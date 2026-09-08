from abc import ABC, abstractmethod
from typing import Any

from fastapi import Response


class BaseExporter(ABC):
    """Abstract strategy for exporting channel requests into test client collections."""

    @abstractmethod
    def export(
        self,
        channel_id: str,
        requests: list[dict[str, Any]],
        base_url: str,
    ) -> Response:
        """Render and package captured requests into an export Response."""
