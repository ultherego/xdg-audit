"""Regression tests for safe quarantine, single-pass references, and local open."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import xdg_audit as audit
from xdg_inspector import open_item_location


class HardeningTests(unittest.TestCase):
    def test_rename_noreplace_prevents_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source, destination = base / "left", base / "right"
            source.write_text("source")
            destination.write_text("destination")
            with self.assertRaises(FileExistsError):
                audit._safe_rename_noreplace(source, destination)
            self.assertEqual(source.read_text(), "source")
            self.assertEqual(destination.read_text(), "destination")

    def test_source_parent_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            actual = base / "actual"; actual.mkdir()
            (actual / "payload").write_text("safe")
            link = base / "link"; link.symlink_to(actual, target_is_directory=True)
            with self.assertRaises(OSError):
                audit._safe_rename_noreplace(link / "payload", base / "moved")
            self.assertTrue((actual / "payload").exists())

    def test_identity_mismatch_refuses_rename(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            source=base/'source';source.write_text('hello')
            with self.assertRaises(ValueError):
                audit._safe_rename_noreplace(source,base/'dest',(1,2,3))
            self.assertTrue(source.exists())

    def test_directory_references_multiple_aliases(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp); conf=home/'.config';(conf/'niri').mkdir(parents=True)
            (conf/'niri'/'config.kdl').write_text('bind "brave-browser" "Ghostty" "brave"')
            with patch.dict(os.environ, {'XDG_CONFIG_HOME':str(conf)}):
                refs=audit.references(home, {'config':conf}, {'brave','brave-browser','Ghostty','go'})
            self.assertIn(str(conf/'niri'/'config.kdl'),refs['brave'])
            self.assertIn(str(conf/'niri'/'config.kdl'),refs['brave-browser'])
            self.assertIn(str(conf/'niri'/'config.kdl'),refs['Ghostty'])
            self.assertFalse(refs['go'])

    def test_no_credential_files_scanned_by_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp);conf=home/'.config'; (conf/'fish').mkdir(parents=True)
            secret=conf/'fish'/'config.kdl.bak';secret.write_text('foobar-app')
            result=audit.references(home,{'config':conf},{'foobar-app'})
            self.assertFalse(result['foobar-app'])

    def test_open_location_does_not_open_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp);entry=home/'test';entry.mkdir()
            with patch('shutil.which',return_value='/usr/bin/xdg-open'), patch('subprocess.Popen') as proc:
                result=open_item_location(entry,home)
            self.assertEqual(result,home)
            self.assertEqual(proc.call_args.args[0],['/usr/bin/xdg-open',str(home)])

    def test_open_location_rejects_symlink_escape(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as external:
            home=Path(tmp);entry=home/'escape';entry.symlink_to(external)
            with self.assertRaises(ValueError):
                open_item_location(entry,home)

if __name__ == '__main__':
    unittest.main()
