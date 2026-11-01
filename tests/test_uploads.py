"""업로드 보관함(ncs_web.uploads.UploadStore) — 토큰 발급·만료·반납. HTTP 없이."""

import unittest
from unittest.mock import patch

from ncs_web.uploads import UploadStore


class UploadStoreTests(unittest.TestCase):
    def test_put_get_release(self):
        store = UploadStore(ttl=60)
        upload = store.put([("a.hwpx", b"x"), ("", b"ignored-empty-name" * 0), ("b.hwpx", b"yy")])
        self.assertEqual([name for name, _ in upload.files], ["a.hwpx", "b.hwpx"])
        self.assertTrue(all(path.read_bytes() for _, path in upload.files))
        self.assertEqual(len(upload.token), len(upload.token.strip()))
        self.assertIs(store.get(upload.token), upload)
        self.assertIsNone(store.get("missing"))
        self.assertTrue(store.release(upload.token))
        self.assertFalse(store.release(upload.token))
        self.assertFalse(upload.directory.exists())

    def test_same_filename_twice_does_not_overwrite(self):
        store = UploadStore()
        upload = store.put([("same.hwpx", b"1"), ("same.hwpx", b"2")])
        self.assertEqual([path.read_bytes() for _, path in upload.files], [b"1", b"2"])
        store.clear()
        self.assertEqual(len(store), 0)

    def test_expiry_sweeps_folder(self):
        store = UploadStore(ttl=10)
        with patch("ncs_web.uploads.time.monotonic", side_effect=[1000.0, 1000.0, 1011.0, 1011.0]):
            upload = store.put([("a.hwpx", b"x")])      # sweep → 1000, expires_at → 1010
            self.assertIsNone(store.get(upload.token))  # sweep → 1011 (만료)
        self.assertFalse(upload.directory.exists())
        self.assertEqual(len(store), 0)

    def test_invalid_inputs(self):
        store = UploadStore(max_bytes=4)
        with self.assertRaises(ValueError):
            store.put([("a.hwpx", b"")])
        with self.assertRaises(ValueError):
            store.put([("..", b"x")])
        with self.assertRaises(ValueError):
            store.put([("a.hwpx", b"12345")])
        self.assertEqual(len(store), 0)


if __name__ == "__main__":
    unittest.main()
