"""Branch cleanup must preserve unmerged work and reject changed-ref races."""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location(
    "branch_cleanup", Path(__file__).resolve().parents[1] / "scripts/cleanup_merged_branches.py")
cleanup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cleanup)
REPO = "owner/project"
HEAD = "a" * 40
MERGE = "b" * 40


def branch(name="feature", sha=HEAD, protected=False):
    return {"name": name, "commit": {"sha": sha}, "protected": protected}


def pull(name="feature", head=HEAD, merge=MERGE, repository=REPO, number=1):
    return {"number": number, "state": "closed", "merged_at": "2026-10-27",
            "head": {"ref": name, "sha": head, "repo": {"full_name": repository}},
            "base": {"ref": "main"}, "merge_commit_sha": merge}


class CleanupPlanTests(unittest.TestCase):
    def plan(self, branches=None, pulls=None, contains=lambda sha: sha == MERGE):
        return cleanup.plan_cleanup(REPO, "main", branches or [branch()],
                                    pulls or [pull()], contains)

    def test_only_unchanged_merged_head_with_merge_in_main_is_selected(self):
        self.assertEqual([p["branch"] for p in self.plan()], ["feature"])
        self.assertEqual(self.plan(contains=lambda _: False), [])
        self.assertEqual(self.plan(branches=[branch(sha="c" * 40)]), [])

    def test_default_protected_publication_and_unknown_protection_are_retained(self):
        for name, protected in [("main", False), ("feature", True), ("feature", None),
                                ("packages", False), ("gh-pages", False)]:
            with self.subTest(name=name, protected=protected):
                self.assertEqual(self.plan([branch(name, protected=protected)], [pull(name)]), [])

    def test_fork_unmerged_and_other_base_prs_are_retained(self):
        fork = pull(repository="someone/fork")
        unmerged = pull()
        unmerged["merged_at"] = None
        other_base = pull()
        other_base["base"]["ref"] = "release"
        for pr in [fork, unmerged, other_base]:
            self.assertEqual(self.plan(pulls=[pr]), [])

    def test_open_head_or_base_dependency_blocks_deletion(self):
        opened = pull(number=2)
        opened["state"] = "open"
        self.assertEqual(self.plan(pulls=[pull(), opened]), [])
        opened["head"]["ref"] = "dependent"
        opened["base"]["ref"] = "feature"
        self.assertEqual(self.plan(pulls=[pull(), opened]), [])

    def test_superseded_exception_requires_exact_reviewed_head_and_merged_replacement(self):
        name, (old, head, replacement, merge) = next(iter(cleanup.SUPERSEDED.items()))
        abandoned = pull(name, head, number=old)
        abandoned["merged_at"] = None
        replacement_pr = pull("replacement", merge=merge, number=replacement)
        planned = self.plan([branch(name, head)], [abandoned, replacement_pr], lambda _: True)
        self.assertEqual(planned[0]["pr"], old)
        self.assertEqual(self.plan([branch(name, "d" * 40)], [abandoned, replacement_pr], lambda _: True), [])
        altered = copy.deepcopy(replacement_pr)
        altered["merge_commit_sha"] = MERGE
        self.assertEqual(self.plan([branch(name, head)], [abandoned, altered], lambda _: True), [])
        self.assertEqual(self.plan([branch(name, head)], [abandoned, replacement_pr], lambda _: False), [])


class AtomicCleanupTests(unittest.TestCase):
    def test_changed_head_preserves_entire_batch_then_valid_cleanup_preserves_main_and_tags(self):
        with tempfile.TemporaryDirectory(prefix="xdg-branch-cleanup-") as temporary:
            root = Path(temporary)
            bare, work = root / "remote.git", root / "work"

            def git(*args, cwd=work):
                return subprocess.check_output(["git", *args], cwd=cwd, stderr=subprocess.STDOUT, text=True).strip()

            git("init", "--bare", "--initial-branch=main", str(bare), cwd=root)
            git("clone", str(bare), str(work), cwd=root)
            git("config", "user.email", "cleanup@example.invalid")
            git("config", "user.name", "Cleanup fixture")
            (work / "sentinel").write_text("keep user data")
            git("add", "sentinel")
            git("commit", "-m", "initial fixture")
            initial = git("rev-parse", "HEAD")
            git("push", "origin", "main", "HEAD:refs/heads/first", "HEAD:refs/heads/second", "HEAD:refs/tags/v-test")
            plan = [{"branch": name, "sha": initial} for name in ["first", "second"]]
            git("commit", "--allow-empty", "-m", "new branch work")
            changed = git("rev-parse", "HEAD")
            git("push", "origin", "HEAD:refs/heads/first")
            with self.assertRaises(subprocess.CalledProcessError):
                cleanup.delete_branches(work, plan, "main")
            with self.assertRaisesRegex(RuntimeError, 'still exists'):
                cleanup.verify_branch_deletions(work, plan)
            self.assertEqual(git("rev-parse", "refs/heads/first", cwd=bare), changed)
            self.assertEqual(git("rev-parse", "refs/heads/second", cwd=bare), initial)
            plan[0]["sha"] = changed
            cleanup.delete_branches(work, plan, "main")
            # A stale local listing must not override the live remote result.
            git('update-ref', 'refs/remotes/origin/first', changed)
            cleanup.verify_branch_deletions(work, plan)
            self.assertEqual(git("for-each-ref", "--format=%(refname)", cwd=bare).splitlines(),
                             ["refs/heads/main", "refs/tags/v-test"])
            self.assertEqual(git("rev-parse", "main", cwd=bare), initial)
            self.assertEqual((work / "sentinel").read_text(), "keep user data")
            git('push', 'origin', 'HEAD:refs/heads/first')
            with self.assertRaisesRegex(RuntimeError, 'still exists'):
                cleanup.verify_branch_deletions(work, plan)
            self.assertEqual(git('rev-parse', 'refs/heads/first', cwd=bare), changed)
            git('remote', 'set-url', 'origin', str(root / 'missing-remote.git'))
            with self.assertRaises(subprocess.CalledProcessError):
                cleanup.verify_branch_deletions(work, plan)

    def test_delete_rejects_default_reserved_invalid_and_duplicate_refs_before_push(self):
        for plan in [[{"branch": "main", "sha": HEAD}],
                     [{"branch": "packages", "sha": HEAD}],
                     [{"branch": "feature", "sha": "bad"}],
                     [{"branch": "feature", "sha": HEAD}] * 2]:
            with self.subTest(plan=plan), self.assertRaises(ValueError):
                cleanup.delete_branches(Path("/nonexistent-cleanup-fixture"), plan, "main")
