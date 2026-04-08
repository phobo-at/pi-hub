from __future__ import annotations

import abc
import logging

from smart_display.models import ProviderSnapshot, utcnow_iso


class BaseProvider(abc.ABC):
    section_name: str
    source_name: str

    def __init__(self, refresh_interval_seconds: int):
        self.refresh_interval_seconds = refresh_interval_seconds
        self.logger = logging.getLogger(f"{__name__}.{self.source_name}")

    def snapshot(
        self,
        *,
        status: str,
        error_message: str | None = None,
        source: str | None = None,
    ) -> ProviderSnapshot:
        return ProviderSnapshot(
            status=status,
            updated_at=utcnow_iso(),
            stale_after_seconds=max(self.refresh_interval_seconds * 2, 30),
            error_message=error_message,
            source=source or self.source_name,
        )

    @abc.abstractmethod
    def refresh(self) -> None:
        raise NotImplementedError
