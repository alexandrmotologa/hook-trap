import uuid
from typing import Any

from fastapi import Response
from fastapi.responses import JSONResponse

from hook_trap.services.export.base import BaseExporter


class PostmanExporter(BaseExporter):
    """Exports channel requests as a Postman Collection v2.1.0."""

    def export(
        self,
        channel_id: str,
        requests: list[dict[str, Any]],
        base_url: str,
    ) -> Response:
        items = []
        for req in requests:
            headers_list = [
                {"key": k, "value": v, "type": "text"}
                for k, v in req.get("headers", {}).items()
                if k.lower() not in ("host", "content-length")
            ]
            body_raw = req.get("body_raw", "")
            path_clean = req.get("path", "").lstrip("/")
            path_segments = path_clean.split("/") if path_clean else []

            is_json = req.get("body_json") is not None
            body_obj = {
                "mode": "raw",
                "raw": body_raw,
                "options": {"raw": {"language": "json" if is_json else "text"}},
            }

            items.append(
                {
                    "name": f"{req['method']} {req['path']} ({req['timestamp'][:19]})",
                    "request": {
                        "method": req["method"],
                        "header": headers_list,
                        "body": body_obj,
                        "url": {
                            "raw": "{{base_url}}" + req["path"],
                            "host": ["{{base_url}}"],
                            "path": path_segments,
                        },
                    },
                    "response": [],
                }
            )

        collection = {
            "info": {
                "_postman_id": str(uuid.uuid4()),
                "name": f"hook-trap - {channel_id}",
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            },
            "item": items,
            "variable": [
                {
                    "key": "base_url",
                    "value": base_url,
                    "type": "string",
                }
            ],
        }

        return JSONResponse(
            content=collection,
            headers={
                "Content-Disposition": f'attachment; filename="hook-trap-{channel_id}-postman.json"'
            },
        )
