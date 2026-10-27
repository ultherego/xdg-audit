#!/usr/bin/env python3
"""Plan obsolete PR branch removal; execution is restricted to main in Actions.

Git's atomic push and per-ref leases protect branches changed after inspection.
No tags, default/protected branches, forks or open-PR dependencies are removed.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.request import Request, urlopen


SHA = re.compile(r"[0-9a-f]{40}\Z")
# PR24 was explicitly closed in favor of merged PR25. This exception is pinned
# to the reviewed historical commits; other unmerged PRs are never eligible.
SUPERSEDED = {
    "feat/read-only-npm-pipx-source-hints": (
        24, "e30f1d7593a213496f682fa4590217cf7619d464",
        25, "f6d34bd387c830e84d46eb0902dad73ed0ae80df",
    ),
}


def plan_cleanup(repository, default_branch, branches, pulls, contains_commit):
    """Require exact closed-PR heads and a merge already contained in main."""
    def own_head(pr):
        return (pr.get("head", {}).get("repo") or {}).get("full_name") == repository

    def merged_here(pr):
        commit = pr.get("merge_commit_sha")
        return (pr.get("state") == "closed" and bool(pr.get("merged_at")) and
                pr.get("base", {}).get("ref") == default_branch and
                isinstance(commit, str) and SHA.fullmatch(commit) and
                contains_commit(commit))

    dependencies = set()
    for pr in pulls:
        if pr.get("state") == "open":
            dependencies.add(pr.get("base", {}).get("ref"))
            if own_head(pr):
                dependencies.add(pr.get("head", {}).get("ref"))
    by_number = {pr.get("number"): pr for pr in pulls}
    plan = []
    for branch in branches:
        name = branch.get("name")
        head = branch.get("commit", {}).get("sha")
        if (not isinstance(name, str) or name in {default_branch, "packages", "gh-pages"} or
                name in dependencies or branch.get("protected") is not False or
                not isinstance(head, str) or not SHA.fullmatch(head)):
            continue
        matches = [pr for pr in pulls if own_head(pr) and
                   pr.get("head", {}).get("ref") == name and
                   pr.get("head", {}).get("sha") == head and
                   merged_here(pr)]
        if matches:
            pr = max(matches, key=lambda p: p["number"])
            plan.append({"branch": name, "sha": head, "pr": pr["number"], "reason": "merged"})
            continue
        exception = SUPERSEDED.get(name)
        if exception:
            old_number, old_head, replacement_number, merge = exception
            old, replacement = by_number.get(old_number, {}), by_number.get(replacement_number, {})
            if (head == old_head and own_head(old) and
                    old.get("state") == "closed" and not old.get("merged_at") and
                    old.get("base", {}).get("ref") == default_branch and
                    old.get("head", {}).get("ref") == name and
                    old.get("head", {}).get("sha") == old_head and
                    own_head(replacement) and replacement.get("merge_commit_sha") == merge and
                    merged_here(replacement)):
                plan.append({"branch": name, "sha": head, "pr": old_number,
                             "reason": f"superseded by merged PR{replacement_number}"})
    return plan


def delete_branches(root, plan, default_branch):
    """Delete the inspected refs together, refusing any changed head."""
    if not plan:
        return
    names = set()
    for item in plan:
        name, sha = item["branch"], item["sha"]
        if (name in {default_branch, "packages", "gh-pages"} or name in names or
                not SHA.fullmatch(sha)):
            raise ValueError("Unsafe or duplicate cleanup ref")
        subprocess.run(["git", "check-ref-format", "refs/heads/" + name],
                       check=True, capture_output=True)
        names.add(name)
    command = ["git", "push", "--atomic"]
    command += [f"--force-with-lease=refs/heads/{item['branch']}:{item['sha']}" for item in plan]
    command += ["origin"] + [":refs/heads/" + item["branch"] for item in plan]
    subprocess.run(command, cwd=root, check=True, timeout=120)


class GitHub:
    def __init__(self, repository, token):
        self.base = "https://api.github.com/repos/" + repository
        self.token = token

    def get(self, path):
        request = Request(self.base + path, headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + self.token,
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "xdg-audit-branch-cleanup",
        })
        with urlopen(request, timeout=30) as response:
            return json.load(response)

    def pages(self, path):
        records = []
        separator = "&" if "?" in path else "?"
        for page in range(1, 101):
            batch = self.get(f"{path}{separator}per_page=100&page={page}")
            if not isinstance(batch, list):
                raise ValueError("Unexpected GitHub collection response")
            records.extend(batch)
            if len(batch) < 100:
                return records
        raise ValueError("GitHub pagination limit reached; refusing incomplete cleanup")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Execute only on main in Actions")
    args = parser.parse_args()
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GITHUB_TOKEN", "")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) or not token:
        parser.error("GITHUB_REPOSITORY and GITHUB_TOKEN are required")
    api = GitHub(repository, token)
    default = api.get("")["default_branch"]
    root = Path(__file__).resolve().parent.parent
    if args.execute:
        if (os.environ.get("GITHUB_ACTIONS") != "true" or default != "main" or
                os.environ.get("GITHUB_REF") != "refs/heads/main" or
                os.environ.get("GITHUB_EVENT_NAME") not in {"push", "workflow_dispatch"}):
            parser.error("Execution requires a trusted main push or manual main workflow in Actions")
        remote = subprocess.check_output(["git", "remote", "get-url", "origin"], cwd=root, text=True).strip()
        if remote not in {f"https://github.com/{repository}", f"https://github.com/{repository}.git"}:
            parser.error("Origin does not match the workflow repository")
    branches = api.pages("/branches")
    pulls = api.pages("/pulls?state=all")
    known = {}

    def contains(commit):
        if commit not in known:
            result = subprocess.run(["git", "merge-base", "--is-ancestor", commit, "HEAD"],
                                    cwd=root, capture_output=True)
            if result.returncode not in {0, 1}:
                raise ValueError("Cannot verify merge ancestry; refusing cleanup")
            known[commit] = result.returncode == 0
        return known[commit]

    plan = plan_cleanup(repository, default, branches, pulls, contains)
    print(json.dumps({"execute": args.execute, "branches": plan}, indent=2))
    if args.execute:
        delete_branches(root, plan, default)
        remaining = {b["name"] for b in api.pages("/branches")}
        if remaining.intersection(item["branch"] for item in plan):
            raise RuntimeError("A selected branch still exists after cleanup")
        print(f"Verified removal of {len(plan)} obsolete branches.")


if __name__ == "__main__":
    main()
