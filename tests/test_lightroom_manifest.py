from __future__ import annotations

import base64
import io
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


def _synthetic_jpeg(width: int, height: int) -> bytes:
    """Render a real JPEG of the requested size so the Pillow pipeline gets
    exercised with non-trivial data (LANCZOS fit, exif_transpose, re-encode).

    Uses a simple gradient + two solid blocks so the output is clearly
    distinguishable from a blank or a 1x1 placeholder.
    """
    from PIL import Image as _Image  # type: ignore

    image = _Image.new("RGB", (width, height), color=(48, 96, 192))
    # Draw a high-frequency pattern so LANCZOS resampling has something real
    # to filter — otherwise the codec might degenerate to a trivial entropy.
    pixels = image.load()
    for y in range(height):
        for x in range(width):
            pixels[x, y] = ((x * 7) % 256, (y * 11) % 256, ((x + y) * 3) % 256)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=82)
    return buffer.getvalue()


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


class PillowPipelineRealBytesTest(unittest.TestCase):
    """Exercise the actual Pillow pipeline — exif_transpose, LANCZOS fit,
    JPEG re-encode — with a non-trivial bitmap. Previous coverage only used
    a 1x1 placeholder which skipped the resize codepath entirely.

    These are the steps the Pi Zero actually runs on every new album photo,
    so if the code path is broken we want to know before the hardware does.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def _make_cache(self, payload: bytes) -> ImageCache:
        def fake_downloader(url: str, timeout_seconds: int):
            return payload, {}

        return ImageCache(
            cache_dir=self.tmp / "screensaver",
            manifest_path=self.tmp / "screensaver" / "manifest.json",
            downloader=fake_downloader,
        )

    def test_oversized_jpeg_is_fit_to_display_size(self) -> None:
        # Typical Lightroom export: 2400x1600 landscape.
        payload = _synthetic_jpeg(2400, 1600)
        cache = self._make_cache(payload)
        entries = cache.sync_remote_images(
            ["https://example.com/big.jpg"], timeout_seconds=5
        )
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(entry.width, 1024)
        self.assertEqual(entry.height, 600)
        # The cached file exists and is a valid JPEG that Pillow can re-open.
        from PIL import Image as _Image  # type: ignore

        with _Image.open(entry.local_path) as reopened:
            self.assertEqual(reopened.size, (1024, 600))
            self.assertEqual(reopened.format, "JPEG")

    def test_portrait_jpeg_is_cover_fit(self) -> None:
        # Portrait photo: Pillow's ImageOps.fit crops to cover, so the final
        # aspect must still be 1024x600.
        payload = _synthetic_jpeg(1200, 1800)
        cache = self._make_cache(payload)
        entries = cache.sync_remote_images(
            ["https://example.com/portrait.jpg"], timeout_seconds=5
        )
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].width, 1024)
        self.assertEqual(entries[0].height, 600)

    def test_small_jpeg_is_upscaled_to_display(self) -> None:
        # Tiny thumbnail: fit() still normalises dimensions, even if the
        # resulting quality is ugly. Important property: no crash.
        payload = _synthetic_jpeg(320, 240)
        cache = self._make_cache(payload)
        entries = cache.sync_remote_images(
            ["https://example.com/thumb.jpg"], timeout_seconds=5
        )
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].width, 1024)
        self.assertEqual(entries[0].height, 600)

    def test_encoded_output_is_bounded(self) -> None:
        # Sanity: after quality=86 re-encode the on-disk file must be
        # smaller than the IMAGE_MAX_BYTES cap (8 MB). A 2400x1600 random
        # pattern is a pessimistic case for JPEG compression.
        payload = _synthetic_jpeg(2400, 1600)
        cache = self._make_cache(payload)
        entries = cache.sync_remote_images(
            ["https://example.com/pattern.jpg"], timeout_seconds=5
        )
        size = Path(entries[0].local_path).stat().st_size
        self.assertLess(size, 1_500_000, f"expected <1.5 MB, got {size}")


class DemoEntriesCacheTest(unittest.TestCase):
    """Plan C2: ``demo_entries`` used to re-walk the demo dir on every
    ``next_entry`` tick. Cache it, but invalidate when the directory mtime
    changes so adding/removing demo files still takes effect."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.demo_dir = self.tmp / "demo"
        self.demo_dir.mkdir()
        (self.demo_dir / "first.jpg").write_bytes(SAMPLE_PNG)

    def _make_cache(self) -> ImageCache:
        return ImageCache(
            cache_dir=self.tmp / "screensaver",
            manifest_path=self.tmp / "screensaver" / "manifest.json",
            demo_dir=self.demo_dir,
            downloader=lambda url, timeout: (SAMPLE_PNG, {}),
        )

    def test_demo_entries_cached_between_calls(self) -> None:
        cache = self._make_cache()
        first = cache.demo_entries()
        self.assertEqual(len(first), 1)

        # Monkey-patch iterdir to detect any re-scan attempts.
        calls = {"count": 0}
        original_iterdir = Path.iterdir

        def counting_iterdir(self_path):
            if self_path == self.demo_dir:
                calls["count"] += 1
            return original_iterdir(self_path)

        Path.iterdir = counting_iterdir  # type: ignore[assignment]
        try:
            second = cache.demo_entries()
            third = cache.demo_entries()
        finally:
            Path.iterdir = original_iterdir  # type: ignore[assignment]

        self.assertEqual(len(second), 1)
        self.assertEqual(len(third), 1)
        self.assertEqual(calls["count"], 0, "cache must not re-walk demo dir")

    def test_demo_cache_invalidates_on_mtime_change(self) -> None:
        cache = self._make_cache()
        self.assertEqual(len(cache.demo_entries()), 1)

        # Add a second file and bump the directory mtime.
        (self.demo_dir / "second.jpg").write_bytes(SAMPLE_PNG)
        import os as _os

        st = self.demo_dir.stat()
        _os.utime(self.demo_dir, (st.st_atime, st.st_mtime + 10))

        refreshed = cache.demo_entries()
        self.assertEqual(len(refreshed), 2)

    def test_demo_cache_returns_empty_if_dir_vanishes(self) -> None:
        cache = self._make_cache()
        self.assertEqual(len(cache.demo_entries()), 1)

        # Delete the demo directory entirely.
        for child in self.demo_dir.iterdir():
            child.unlink()
        self.demo_dir.rmdir()

        self.assertEqual(cache.demo_entries(), [])


if __name__ == "__main__":
    unittest.main()
