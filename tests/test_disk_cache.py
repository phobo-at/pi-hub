from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from smart_display.cache.disk_cache import DiskCache
from smart_display.cache.image_cache import ImageCache


class DiskCacheCorruptionTest(unittest.TestCase):
    """Plan B3 / S2: corrupt JSON must not crash boot — it gets quarantined
    aside and the caller rehydrates from a fresh source."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = Path(self._tmp.name)
        self.cache_path = self.tmp_path / "state.json"

    def test_load_returns_none_on_missing_file(self) -> None:
        cache = DiskCache(self.cache_path)
        self.assertIsNone(cache.load())

    def test_save_then_load_roundtrip(self) -> None:
        cache = DiskCache(self.cache_path)
        cache.save({"hello": "world", "n": 1})
        self.assertEqual(cache.load(), {"hello": "world", "n": 1})

    def test_load_returns_none_on_corrupt_json(self) -> None:
        self.cache_path.write_text("{not valid json", encoding="utf-8")
        cache = DiskCache(self.cache_path)
        self.assertIsNone(cache.load())

    def test_corrupt_file_renamed_aside(self) -> None:
        self.cache_path.write_text("garbage", encoding="utf-8")
        cache = DiskCache(self.cache_path)
        cache.load()

        # Original file is gone; a .corrupt-<ts> sibling carries the bytes.
        self.assertFalse(self.cache_path.exists())
        siblings = list(self.tmp_path.glob("state.json.corrupt-*"))
        self.assertEqual(len(siblings), 1)
        self.assertEqual(siblings[0].read_text(encoding="utf-8"), "garbage")

    def test_next_save_succeeds_after_quarantine(self) -> None:
        # Real failure pattern: boot hits corrupt file, provider re-fetches,
        # StateStore persists fresh data. The cache path must be writable again.
        self.cache_path.write_text("{", encoding="utf-8")
        cache = DiskCache(self.cache_path)
        self.assertIsNone(cache.load())
        cache.save({"fresh": True})
        self.assertEqual(cache.load(), {"fresh": True})


class ImageCacheManifestRobustnessTest(unittest.TestCase):
    """Plan B3: malformed manifest entries must be skipped, not crash boot."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.cache_dir = self.tmp / "cache"
        self.cache_dir.mkdir()
        self.manifest_path = self.cache_dir / "manifest.json"

    def _fake_download(self, url: str, timeout_seconds: int) -> tuple[bytes, dict[str, str]]:
        raise AssertionError("downloader must not be called during manifest load")

    def _make_image_file(self, name: str) -> Path:
        path = self.cache_dir / name
        path.write_bytes(b"\x89PNG\r\n")
        return path

    def test_manifest_corrupt_json_returns_empty(self) -> None:
        self.manifest_path.write_text("not json", encoding="utf-8")
        cache = ImageCache(
            self.cache_dir,
            self.manifest_path,
            downloader=self._fake_download,
        )
        self.assertEqual(cache.entries(), [])
        # DiskCache quarantined the corrupt file, so a fresh save works.
        self.assertFalse(self.manifest_path.exists() and
                         self.manifest_path.read_text(encoding="utf-8") == "not json")

    def test_manifest_bad_entry_skipped_good_kept(self) -> None:
        good_image = self._make_image_file("good.jpg")
        manifest_body = [
            {
                "id": "good",
                "source_url": "https://example.com/good.jpg",
                "local_path": str(good_image),
                "public_path": "/media/screensaver/good.jpg",
                "width": 1024,
                "height": 600,
            },
            # Bad: width is not coercible to int
            {
                "id": "bad",
                "source_url": "https://example.com/bad.jpg",
                "local_path": str(self._make_image_file("bad.jpg")),
                "public_path": "/media/screensaver/bad.jpg",
                "width": "broken",
                "height": 600,
            },
            # Bad: not even a dict
            "totally wrong",
        ]
        self.manifest_path.write_text(json.dumps(manifest_body), encoding="utf-8")

        cache = ImageCache(
            self.cache_dir,
            self.manifest_path,
            downloader=self._fake_download,
        )

        ids = [entry.id for entry in cache.entries()]
        self.assertEqual(ids, ["good"])
        # The manifest was rewritten to drop the broken records.
        on_disk = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(len(on_disk), 1)
        self.assertEqual(on_disk[0]["id"], "good")

    def test_manifest_non_list_root_resets(self) -> None:
        self.manifest_path.write_text('{"oops": "dict"}', encoding="utf-8")
        cache = ImageCache(
            self.cache_dir,
            self.manifest_path,
            downloader=self._fake_download,
        )
        self.assertEqual(cache.entries(), [])
        # Reset to an empty list so subsequent syncs have clean ground.
        self.assertEqual(
            json.loads(self.manifest_path.read_text(encoding="utf-8")), []
        )


if __name__ == "__main__":
    unittest.main()
