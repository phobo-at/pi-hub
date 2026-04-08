from __future__ import annotations

import hashlib
import io
import logging
import random
from pathlib import Path
from typing import Callable
from urllib import error as urllib_error
from urllib import request as urllib_request

from smart_display.cache.disk_cache import DiskCache
from smart_display.models import PhotoManifestEntry


logger = logging.getLogger(__name__)


try:
    from PIL import Image, ImageOps  # type: ignore
except ImportError:  # pragma: no cover
    Image = None
    ImageOps = None


DownloadResult = tuple[bytes, dict[str, str]]


class ImageCache:
    def __init__(
        self,
        cache_dir: str | Path,
        manifest_path: str | Path,
        *,
        display_size: tuple[int, int] = (1024, 600),
        downloader: Callable[[str, int], DownloadResult] | None = None,
        demo_dir: str | Path | None = None,
    ):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.demo_dir = Path(demo_dir) if demo_dir else None
        self.manifest_cache = DiskCache(manifest_path)
        self.display_size = display_size
        self._downloader = downloader or self._default_download
        self._random = random.Random()
        self._entries = self._load_manifest()

    def entries(self) -> list[PhotoManifestEntry]:
        return list(self._entries)

    def count(self) -> int:
        return len(self._entries)

    def sync_remote_images(
        self, source_urls: list[str], *, timeout_seconds: int
    ) -> list[PhotoManifestEntry]:
        unique_urls = list(dict.fromkeys(source_urls))
        existing = {
            entry.source_url: entry
            for entry in self._entries
            if Path(entry.local_path).exists()
        }

        next_entries: list[PhotoManifestEntry] = []
        used_filenames: set[str] = set()
        for url in unique_urls:
            cached = existing.get(url)
            if cached:
                next_entries.append(cached)
                used_filenames.add(Path(cached.local_path).name)
                continue
            downloaded = self._download_and_prepare(url, timeout_seconds=timeout_seconds)
            if downloaded:
                next_entries.append(downloaded)
                used_filenames.add(Path(downloaded.local_path).name)

        self._entries = next_entries
        self._cleanup_unused_files(used_filenames)
        self.manifest_cache.save([entry.to_dict() for entry in self._entries])
        return self.entries()

    def next_entry(self, *, include_demo: bool = True) -> PhotoManifestEntry | None:
        pool = self._entries
        if not pool and include_demo:
            pool = self.demo_entries()
        if not pool:
            return None
        return self._random.choice(pool)

    def demo_entries(self) -> list[PhotoManifestEntry]:
        if not self.demo_dir or not self.demo_dir.exists():
            return []
        entries: list[PhotoManifestEntry] = []
        for path in sorted(self.demo_dir.iterdir()):
            if path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".svg"}:
                continue
            entries.append(
                PhotoManifestEntry(
                    id=path.stem,
                    source_url=path.name,
                    local_path=str(path.resolve()),
                    public_path=f"/static/images/demo-screensaver/{path.name}",
                    width=self.display_size[0],
                    height=self.display_size[1],
                    content_hash=path.stem,
                )
            )
        return entries

    def entry_for_filename(self, filename: str) -> PhotoManifestEntry | None:
        for entry in self._entries:
            if Path(entry.local_path).name == filename:
                return entry
        return None

    def _load_manifest(self) -> list[PhotoManifestEntry]:
        # DiskCache.load() already quarantines unparseable JSON (Plan S2).
        # Here we additionally defend against per-entry schema drift — a
        # single malformed record must not poison the whole manifest.
        raw = self.manifest_cache.load()
        if not isinstance(raw, list):
            if raw is not None:
                logger.warning(
                    "image manifest at %s has unexpected shape (%s) — resetting",
                    self.manifest_cache.path,
                    type(raw).__name__,
                )
                self.manifest_cache.save([])
            return []

        entries: list[PhotoManifestEntry] = []
        skipped = 0
        for item in raw:
            if not isinstance(item, dict):
                skipped += 1
                continue
            local_path_value = str(item.get("local_path", ""))
            if not local_path_value or not Path(local_path_value).exists():
                skipped += 1
                continue
            try:
                entries.append(PhotoManifestEntry.from_dict(item))
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning(
                    "image manifest entry dropped (%s): %s", exc, item
                )
                skipped += 1

        if skipped:
            self.manifest_cache.save([entry.to_dict() for entry in entries])
        return entries

    def _cleanup_unused_files(self, used_filenames: set[str]) -> None:
        for path in self.cache_dir.iterdir():
            if path.is_file() and path.name != "manifest.json" and path.name not in used_filenames:
                path.unlink(missing_ok=True)

    def _download_and_prepare(
        self, source_url: str, *, timeout_seconds: int
    ) -> PhotoManifestEntry | None:
        payload, headers = self._downloader(source_url, timeout_seconds)
        digest = hashlib.sha1(source_url.encode("utf-8")).hexdigest()[:16]
        filename = f"{digest}.jpg"
        local_path = self.cache_dir / filename
        width, height = self.display_size

        if Image is not None and ImageOps is not None:
            with Image.open(io.BytesIO(payload)) as image:
                prepared = ImageOps.exif_transpose(image).convert("RGB")
                fitted = ImageOps.fit(
                    prepared, self.display_size, method=Image.Resampling.LANCZOS
                )
                fitted.save(local_path, format="JPEG", quality=86, optimize=True)
                width, height = fitted.size
        else:  # pragma: no cover
            local_path.write_bytes(payload)

        return PhotoManifestEntry(
            id=digest,
            source_url=source_url,
            local_path=str(local_path.resolve()),
            public_path=f"/media/screensaver/{filename}",
            width=width,
            height=height,
            content_hash=hashlib.sha1(payload).hexdigest(),
            etag=headers.get("etag"),
            last_modified=headers.get("last-modified"),
        )

    def _default_download(self, url: str, timeout_seconds: int) -> DownloadResult:
        request = urllib_request.Request(
            url,
            headers={"User-Agent": "pi-hub-smart-display/0.1"},
        )
        try:
            with urllib_request.urlopen(request, timeout=timeout_seconds) as response:
                payload = response.read()
                headers = {key.lower(): value for key, value in response.headers.items()}
                return payload, headers
        except urllib_error.URLError as exc:  # pragma: no cover
            raise RuntimeError(f"image download failed for {url}: {exc}") from exc

