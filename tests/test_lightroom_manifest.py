from __future__ import annotations

import base64
import tempfile
import unittest
from pathlib import Path

from smart_display.cache.image_cache import (
    _INITIAL_BACKOFF_SECONDS,
    _MAX_BACKOFF_SECONDS,
    _compute_next_retry,
    ImageCache,
)
from smart_display.providers.lightroom_source import extract_image_urls


SAMPLE_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7Z4xQAAAAASUVORK5CYII="
)


class LightroomManifestTest(unittest.TestCase):
    def test_extract_image_urls_deduplicates_candidates(self) -> None:
        html = """
        <html>
          <head><meta property="og:image" content="/img/cover.jpg"></head>
          <body><img src="/img/cover.jpg"><img data-src="https://example.com/img/second.png"></body>
        </html>
        """
        urls = extract_image_urls(html, "https://example.com/gallery")
        self.assertEqual(
            urls,
            [
                "https://example.com/img/cover.jpg",
                "https://example.com/img/second.png",
            ],
        )

    def test_sync_remote_images_reuses_existing_manifest_entries(self) -> None:
        calls: list[str] = []

        def fake_downloader(url: str, timeout_seconds: int):
            calls.append(url)
            return SAMPLE_PNG, {}

        with tempfile.TemporaryDirectory() as temp_dir:
            cache = ImageCache(
                cache_dir=Path(temp_dir) / "screensaver",
                manifest_path=Path(temp_dir) / "screensaver" / "manifest.json",
                downloader=fake_downloader,
            )
            urls = [
                "https://example.com/a.jpg",
                "https://example.com/b.jpg",
            ]
            cache.sync_remote_images(urls, timeout_seconds=5)
            cache.sync_remote_images(urls, timeout_seconds=5)

            self.assertEqual(calls, urls)
            self.assertEqual(cache.count(), 2)


class PerTickDownloadLimitTest(unittest.TestCase):
    """Plan B9: the provider may only fetch a small number of new images
    per refresh tick so the Pi Zero isn't monopolised by a fresh album
    import. Already-cached entries stay visible across ticks."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def _make_cache(self, downloader):
        return ImageCache(
            cache_dir=self.tmp / "screensaver",
            manifest_path=self.tmp / "screensaver" / "manifest.json",
            downloader=downloader,
        )

    def test_per_tick_budget_caps_new_downloads(self) -> None:
        calls: list[str] = []

        def fake_downloader(url: str, timeout_seconds: int):
            calls.append(url)
            return SAMPLE_PNG, {}

        cache = self._make_cache(fake_downloader)
        urls = [
            "https://example.com/a.jpg",
            "https://example.com/b.jpg",
            "https://example.com/c.jpg",
        ]
        cache.sync_remote_images(urls, timeout_seconds=5, max_new_downloads=1)
        self.assertEqual(cache.count(), 1)
        self.assertEqual(len(calls), 1)

        cache.sync_remote_images(urls, timeout_seconds=5, max_new_downloads=1)
        self.assertEqual(cache.count(), 2)
        self.assertEqual(len(calls), 2)

        cache.sync_remote_images(urls, timeout_seconds=5, max_new_downloads=1)
        self.assertEqual(cache.count(), 3)
        self.assertEqual(len(calls), 3)

    def test_unbounded_budget_downloads_everything(self) -> None:
        calls: list[str] = []

        def fake_downloader(url: str, timeout_seconds: int):
            calls.append(url)
            return SAMPLE_PNG, {}

        cache = self._make_cache(fake_downloader)
        cache.sync_remote_images(
            ["https://example.com/a.jpg", "https://example.com/b.jpg"],
            timeout_seconds=5,
        )
        self.assertEqual(len(calls), 2)


class DownloadFailureBackoffTest(unittest.TestCase):
    """Plan B9: payload/decode failures must not crash the refresh loop,
    must be recorded, and must respect exponential backoff so the Pi
    doesn't thrash on a broken album."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self._now = 1_000_000.0

    def _now_fn(self) -> float:
        return self._now

    def _make_cache(self, downloader):
        return ImageCache(
            cache_dir=self.tmp / "screensaver",
            manifest_path=self.tmp / "screensaver" / "manifest.json",
            downloader=downloader,
            clock=self._now_fn,
        )

    def test_bad_payload_is_recorded_and_skipped(self) -> None:
        def fake_downloader(url: str, timeout_seconds: int):
            return b"not an image", {}

        cache = self._make_cache(fake_downloader)
        cache.sync_remote_images(["https://example.com/bad.jpg"], timeout_seconds=5)
        self.assertEqual(cache.count(), 0)
        failures = cache.failed_urls()
        self.assertIn("https://example.com/bad.jpg", failures)
        self.assertEqual(failures["https://example.com/bad.jpg"]["attempts"], 1)

    def test_failure_blocks_retries_until_backoff_elapses(self) -> None:
        call_count = {"count": 0}

        def fake_downloader(url: str, timeout_seconds: int):
            call_count["count"] += 1
            return b"not an image", {}

        cache = self._make_cache(fake_downloader)
        cache.sync_remote_images(["https://example.com/bad.jpg"], timeout_seconds=5)
        self.assertEqual(call_count["count"], 1)

        # Within the backoff window: do not retry.
        self._now += 10.0
        cache.sync_remote_images(["https://example.com/bad.jpg"], timeout_seconds=5)
        self.assertEqual(call_count["count"], 1)

        # Past the backoff window: retry, attempts increments.
        self._now += _INITIAL_BACKOFF_SECONDS + 5.0
        cache.sync_remote_images(["https://example.com/bad.jpg"], timeout_seconds=5)
        self.assertEqual(call_count["count"], 2)
        self.assertEqual(
            cache.failed_urls()["https://example.com/bad.jpg"]["attempts"], 2
        )

    def test_successful_retry_clears_failure(self) -> None:
        # First call fails, second call (well past backoff) succeeds.
        attempts = {"count": 0}

        def fake_downloader(url: str, timeout_seconds: int):
            attempts["count"] += 1
            if attempts["count"] == 1:
                return b"not an image", {}
            return SAMPLE_PNG, {}

        cache = self._make_cache(fake_downloader)
        cache.sync_remote_images(["https://example.com/one.jpg"], timeout_seconds=5)
        self.assertEqual(cache.count(), 0)
        self.assertIn("https://example.com/one.jpg", cache.failed_urls())

        self._now += _INITIAL_BACKOFF_SECONDS + 5.0
        cache.sync_remote_images(["https://example.com/one.jpg"], timeout_seconds=5)
        self.assertEqual(cache.count(), 1)
        self.assertNotIn("https://example.com/one.jpg", cache.failed_urls())

    def test_failures_prune_when_url_leaves_source_list(self) -> None:
        def fake_downloader(url: str, timeout_seconds: int):
            return b"not an image", {}

        cache = self._make_cache(fake_downloader)
        cache.sync_remote_images(["https://example.com/gone.jpg"], timeout_seconds=5)
        self.assertIn("https://example.com/gone.jpg", cache.failed_urls())

        cache.sync_remote_images([], timeout_seconds=5)
        self.assertNotIn("https://example.com/gone.jpg", cache.failed_urls())


class RetryBackoffMathTest(unittest.TestCase):
    def test_backoff_doubles_each_attempt(self) -> None:
        self.assertEqual(_compute_next_retry(1), _INITIAL_BACKOFF_SECONDS)
        self.assertEqual(_compute_next_retry(2), _INITIAL_BACKOFF_SECONDS * 2)
        self.assertEqual(_compute_next_retry(3), _INITIAL_BACKOFF_SECONDS * 4)

    def test_backoff_caps_at_24h(self) -> None:
        # 60 * 2^20 is way past 24 h — must clamp.
        self.assertEqual(_compute_next_retry(20), _MAX_BACKOFF_SECONDS)


if __name__ == "__main__":
    unittest.main()
