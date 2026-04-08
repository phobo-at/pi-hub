from __future__ import annotations

import base64
import tempfile
import unittest
from pathlib import Path

from smart_display.cache.image_cache import ImageCache
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


if __name__ == "__main__":
    unittest.main()

