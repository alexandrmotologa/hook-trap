from typing import Any

from fastapi import HTTPException, Response

from hook_trap.models import ExportFormat
from hook_trap.services.export.base import BaseExporter
from hook_trap.services.export.bruno import BrunoExporter
from hook_trap.services.export.json_dump import JsonExporter
from hook_trap.services.export.postman import PostmanExporter


class ExportService:
    """Service orchestrating collection exports using format strategies."""

    def __init__(self) -> None:
        self._exporters: dict[str, BaseExporter] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        self.register(ExportFormat.POSTMAN, PostmanExporter())
        self.register(ExportFormat.BRUNO, BrunoExporter())
        self.register(ExportFormat.JSON, JsonExporter())

    def register(self, format_name: str, exporter: BaseExporter) -> None:
        """Register a format exporter."""
        self._exporters[format_name.lower().strip()] = exporter

    def export(
        self,
        format_name: str,
        channel_id: str,
        requests: list[dict[str, Any]],
        base_url: str,
    ) -> Response:
        """Export requests in the requested format."""
        exporter = self._exporters.get(format_name.lower().strip())
        if not exporter:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported export format: {format_name}",
            )
        return exporter.export(channel_id=channel_id, requests=requests, base_url=base_url)


# Default singleton instance
export_service = ExportService()
