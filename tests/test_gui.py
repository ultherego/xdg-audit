"""GUI dispatcher tests: no real desktop or GUI bindings needed."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import xdg_audit as engine
import xdg_gui as gui


class GuiTests(unittest.TestCase):
    def test_prefer_qt_for_kde(self):
        self.assertEqual(gui.choose_backend('KDE Plasma', ['gtk4','qt6','tk']), 'qt6')
        self.assertEqual(gui.choose_backend('LXQt', ['gtk4','qt6','tk']), 'qt6')

    def test_prefer_gtk_for_gnome_niri(self):
        for desktop in ('GNOME', 'Niri', 'Hyprland', 'Sway', 'XFCE'):
            self.assertEqual(gui.choose_backend(desktop, ['tk','qt6','gtk4']), 'gtk4')

    def test_fallback_when_primary_missing(self):
        self.assertEqual(gui.choose_backend('KDE Plasma',['gtk3','tk']), 'gtk3')
        self.assertEqual(gui.choose_backend('GNOME',['tk']), 'tk')
        self.assertIsNone(gui.choose_backend('Niri',[]))

    def test_runtime_niri_wayland_without_xwayland(self):
        with patch.object(gui,'available_backends',return_value=['gtk4']):
            data=gui.detect_gui_runtime({'XDG_CURRENT_DESKTOP':'niri','WAYLAND_DISPLAY':'wayland-1'})
        self.assertEqual(data['session'],'Wayland')
        self.assertEqual(data['selected'],'gtk4')

    def test_no_args_opens_gui(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(engine,'check_no_root'):
            # default home mock avoids relying on current (possibly root) HOME
            with patch.object(engine.Path,'home',return_value=Path(temp)):
                with patch.object(gui,'launch_gui',return_value=73) as start:
                    self.assertEqual(engine.main([]),73)
                    self.assertTrue(start.called)

    def test_cli_scope_does_not_open_gui(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(engine,'check_no_root'):
            with patch.object(gui,'launch_gui') as start, patch.object(engine,'scan',return_value=([],{},{'pacman_packages':0,'flatpak_entries':0,'removed_package_names':0,'desktop_names':0})):
                self.assertEqual(engine.main(['--home',temp,'--scope','config','--quick']),0)
                start.assert_not_called()

    def test_quarantine_restore_never_overwrites(self):
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp)
            (home/'.config').mkdir()
            source=home/'.config'/'test-app'
            source.mkdir()
            (source/'config.ini').write_text('secret=keep')
            roots=engine.xdg_roots(home)
            items=[engine.Item(scope='config', path=source,state='CANDIDATE', removable=True,
                               identity=engine.stat_tuple(source))] if hasattr(engine,'stat_tuple') else []
            if not items:
                st=source.lstat()
                import stat
                items=[engine.Item(scope='config',path=source,state='CANDIDATE',removable=True,
                         identity=(st.st_dev,st.st_ino,stat.S_IFMT(st.st_mode)))]
            with patch.object(engine, 'read_active_names', return_value=({'unrelated'},set(),set(),set(),set(),set(),set(),{'unrelated'})):
                result=engine.commit_quarantine(items,roots,home,emit=lambda x:None)
            self.assertEqual(len(result['moved']),1)
            self.assertEqual(len(engine.quarantine_runs(home,roots)),1)
            source.mkdir()
            (source/'new').write_text('keep me')
            restored=engine.restore_quarantine_run(home,roots,result['run_id'],emit=lambda x:None)
            self.assertEqual(restored['restored'],0)
            self.assertTrue((source/'new').exists())
            (source/'new').unlink();source.rmdir()
            restored=engine.restore_quarantine_run(home,roots,result['run_id'],emit=lambda x:None)
            self.assertEqual(restored['restored'],1)
            self.assertEqual((source/'config.ini').read_text(),'secret=keep')

if __name__=='__main__':unittest.main()
