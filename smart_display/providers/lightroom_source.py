from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from smart_display.cache.image_cache import ImageCache
from smart_display.config import AppConfig
from smart_display.providers.base import BaseProvider
from smart_display.state_store import StateStore


IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")


class _ImageCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "img":
            for name in ("src", "data-src", "data-image", "data-fullres"):
                if attributes.get(name):
                    self.urls.append(attributes[name] or "")
        if tag == "source" and attributes.get("srcset"):
            self.urls.extend(item.split(" ")[0] for item in attributes["srcset"].split(","))
        if tag == "meta" and attributes.get("property") in {"og:image", "twitter:image"}:
            content = attributes.get("content")
            if content:
                self.urls.append(content)


def extract_image_urls(html_text: str, base_url: str) -> list[str]:
    parser = _ImageCollector()
    parser.feed(html_text)
    candidates = list(parser.urls)

    escaped_urls = re.findall(
        r"https?:\\\\?/\\\\?/[^\"'\\s]+?\.(?:jpg|jpeg|png|webp)",
        html_text,
        re.IGNORECASE,
    )
    candidates.extend(url.replace("\\/", "/") for url in escaped_urls)

    normalized: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        candidate = html.unescape(candidate).strip()
        if not candidate:
            continue
        absolute_url = urllib_parse.urljoin(base_url, candidate)
        lowered = absolute_url.lower()
        if not lowered.startswith(("http://", "https://")):
            continue
        if not lowered.split("?")[0].endswith(IMAGE_EXTENSIONS):
            continue
        if absolute_url in seen:
            continue
        seen.add(absolute_url)
        normalized.append(absolute_url)
    return normalized


class LightroomSourceProvider(BaseProvider):
    section_name = "screensaver"
    source_name = "lightroom"

    def __init__(self, config: AppConfig, state_store: StateStore, image_cache: ImageCache):
        super().__init__(config.refresh_intervals.lightroom_seconds)
        self.config = config
        self.state_store = state_store
        self.image_cache = image_cache

    def refresh(self) -> None:
        available_demo = (
            len(self.image_cache.demo_entries())
            if self.config.screensaver.demo_images_enabled
            else 0
        )

        if not self.config.screensaver.enabled:
            self.state_store.set_provider_snapshot(
                self.section_name,
                self.snapshot(status="empty", error_message="Screensaver deaktiviert."),
            )
            self.state_store.set_screensaver_photo_count(self.image_cache.count())
            return

        if not self.config.screensaver.source_url:
            self.state_store.set_provider_snapshot(
                self.section_name,
                self.snapshot(
                    status="empty",
                    error_message="Keine Lightroom-Quelle konfiguriert.",
                ),
            )
            self.state_store.set_screensaver_photo_count(
                self.image_cache.count() or available_demo
            )
            return

        try:
            request = urllib_request.Request(
                self.config.screensaver.source_url,
                headers={"User-Agent": "pi-hub-smart-display/0.1"},
            )
            with urllib_request.urlopen(
                request, timeout=self.config.screensaver.timeout_seconds
            ) as response:
                html_text = response.read().decode("utf-8", errors="ignore")
            image_urls = extract_image_urls(html_text, self.config.screensaver.source_url)
            if not image_urls:
                raise RuntimeError("Keine Bild-URLs im Lightroom-Album gefunden.")
            entries = self.image_cache.sync_remote_images(
                image_urls, timeout_seconds=self.config.screensaver.timeout_seconds
            )
            status = "ok" if entries else "empty"
            self.state_store.set_provider_snapshot(self.section_name, self.snapshot(status=status))
            self.state_store.set_screensaver_photo_count(len(entries))
        except (urllib_error.URLError, RuntimeError) as exc:
            self.logger.exception("screensaver refresh failed")
            fallback_status = "stale" if self.image_cache.count() > 0 else "error"
            self.state_store.set_provider_snapshot(
                self.section_name,
                self.snapshot(status=fallback_status, error_message=str(exc)),
            )
            self.state_store.set_screensaver_photo_count(
                self.image_cache.count() or available_demo
            )

