from typing import Any

from fastapi import Response
from fastapi.responses import JSONResponse

from hook_trap.services.export.base import BaseExporter


class JsonExporter(BaseExporter):
    """Exports raw JSON array dump of captured requests."""

    def export(
        self,
        channel_id: str,
        requests: list[dict[str, Any]],
        base_url: str,
    ) -> Response:
        return JSONResponse(
            content=requests,
            headers={"Content-Disposition": f'attachment; filename="hook-trap-{channel_id}.json"'},
        )
