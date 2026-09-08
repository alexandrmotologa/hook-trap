from typing import Any

from fastapi import Response
from fastapi.responses import JSONResponse

from hook_trap.services.export.base import BaseExporter


class BrunoExporter(BaseExporter):
    """Exports channel requests as a Bruno collection JSON."""

    def export(
        self,
        channel_id: str,
        requests: list[dict[str, Any]],
        base_url: str,
    ) -> Response:
        items = []
        for req in requests:
            headers_dict = {
                k: v
                for k, v in req.get("headers", {}).items()
                if k.lower() not in ("host", "content-length")
            }
            items.append(
                {
                    "name": f"{req['method']}_{req['id'][:8]}",
                    "request": {
                        "method": req["method"],
                        "url": f"{base_url}{req['path']}",
                        "headers": headers_dict,
                        "body": req.get("body_raw", ""),
                    },
                }
            )

        bruno_data = {
            "version": "1",
            "name": f"hook-trap-{channel_id}",
            "type": "collection",
            "items": items,
        }

        return JSONResponse(
            content=bruno_data,
            headers={
                "Content-Disposition": f'attachment; filename="hook-trap-{channel_id}-bruno.json"'
            },
        )
