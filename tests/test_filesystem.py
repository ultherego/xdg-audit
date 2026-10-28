"""Descriptor-bound filesystem evidence and non-secret mount reporting."""
import errno
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import uuid

import xdg_filesystem as filesystem

BINDING = {"kind": "btrfs", "fsid": "11111111-2222-3333-4444-555555555555",
           "subvolume_id": 256, "subvolume_uuid": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}


class FilesystemTests(unittest.TestCase):
    def test_read_only_btrfs_uapi_fields_and_zeroed_input_buffers(self):
        def ioctl(fd, command, data, mutate):
            self.assertTrue(mutate)
            self.assertFalse(any(data))
            if command == filesystem.BTRFS_FS_INFO:
                self.assertEqual(len(data), 1024)
                data[16:32] = uuid.UUID(BINDING['fsid']).bytes
            elif command == filesystem.BTRFS_GET_SUBVOL_INFO:
                self.assertEqual(len(data), 504)
                struct.pack_into('=Q', data, 0, BINDING['subvolume_id'])
                data[296:312] = uuid.UUID(BINDING['subvolume_uuid']).bytes
            else:
                self.fail('Unexpected ioctl; only read-only FS/subvolume requests allowed')
        with patch.object(filesystem.platform, 'machine', return_value='x86_64'), \
                patch.object(filesystem.fcntl, 'ioctl', side_effect=ioctl):
            self.assertEqual(filesystem.btrfs_identity(17), BINDING)

    def test_non_btrfs_and_unsupported_architecture_do_not_invent_identity(self):
        with patch.object(filesystem.fcntl, 'ioctl', side_effect=OSError(errno.ENOTTY, 'not Btrfs')):
            self.assertIsNone(filesystem.btrfs_identity(17))
        with patch.object(filesystem.platform, 'machine', return_value='unsupported'), \
                patch.object(filesystem.fcntl, 'ioctl') as ioctl:
            self.assertIsNone(filesystem.btrfs_identity(17))
            ioctl.assert_not_called()

    def test_missing_uuid_or_malformed_binding_never_validates(self):
        for value in [None, {}, {**BINDING, 'subvolume_id': True},
                      {**BINDING, 'fsid': '00000000-0000-0000-0000-000000000000'},
                      {**BINDING, 'subvolume_uuid': 'bad'}, {**BINDING, 'extra': 'untrusted'}]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                filesystem.validate_identity(value)

    def test_mount_is_selected_by_descriptor_and_credential_fields_are_omitted(self):
        mounts = ('41 1 0:9 / /elsewhere rw - cifs //user:password@server/share rw,password=secret\n'
                  '42 1 0:10 /sub\\040volume /home\\040name rw,nosuid - btrfs /dev/secret rw,secret=value\n')
        with tempfile.TemporaryDirectory() as temporary:
            info = Path(temporary).stat()
            with patch.object(filesystem, '_proc_text', side_effect=['pos: 0\nmnt_id: 42\n', mounts]):
                result = filesystem.mount_context(17, info)
            self.assertEqual(result['mount_id'], 42)
            self.assertEqual(result['filesystem_type'], 'btrfs')
            self.assertEqual(result['root'], '/sub volume')
            self.assertEqual(result['mountpoint'], '/home name')
            self.assertFalse(result['persistent'])
            self.assertNotIn('secret', str(result))
            self.assertNotIn('password', str(result))

    def test_symlink_file_and_ancestor_are_never_followed_for_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'real').mkdir()
            (root / 'real/file').write_text('untouched')
            (root / 'link').symlink_to(root / 'real', target_is_directory=True)
            (root / 'file-link').symlink_to(root / 'real/file')
            for path in [root / 'link/file', root / 'file-link']:
                with self.subTest(path=path), self.assertRaises((OSError, ValueError)), \
                        patch.object(filesystem, 'btrfs_identity') as ioctl:
                    filesystem.filesystem_context(path)
                ioctl.assert_not_called()
            self.assertEqual((root / 'real/file').read_text(), 'untouched')

    def test_actual_descriptor_context_is_read_only_and_identity_mismatch_refuses(self):
        with tempfile.TemporaryDirectory() as temporary:
            file = Path(temporary) / 'file'
            file.write_bytes(b'preserved bytes')
            info = file.stat()
            context = filesystem.filesystem_context(file)
            self.assertEqual(context['stat_identity'][:2], [info.st_dev, info.st_ino])
            self.assertEqual(context['mount']['stat_major_minor'], f'{os.major(info.st_dev)}:{os.minor(info.st_dev)}')
            with self.assertRaises(ValueError):
                filesystem.filesystem_identity(file, [info.st_dev, info.st_ino + 1, 32768])
            self.assertEqual(file.read_bytes(), b'preserved bytes')
