from typing import Any

from hook_trap.repositories.base import DatabaseManager, utc_now_iso


class ChannelRepository:
    """Repository handling persistence and configuration for channels."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        self._db = db_manager

    async def get(self, channel_id: str) -> dict[str, Any] | None:
        """Retrieve persisted channel configuration."""
        async with self._db.connection() as conn:
            query = """
                SELECT channel_id, name, auto_forward_url, max_requests,
                       custom_response_mode, custom_response_body,
                       custom_response_status, custom_response_content_type,
                       signing_secret, signing_provider,
                       created_at, updated_at
                FROM channels
                WHERE channel_id = ?;
            """
            async with conn.execute(query, (channel_id,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                data = dict(row)
                if data.get("max_requests") is None:
                    data["max_requests"] = 500
                if not data.get("custom_response_mode"):
                    data["custom_response_mode"] = "default"
                if data.get("custom_response_status") is None:
                    data["custom_response_status"] = 200
                if not data.get("custom_response_content_type"):
                    data["custom_response_content_type"] = "application/json"
                return data

    async def upsert(
        self,
        channel_id: str,
        name: str | None = None,
        auto_forward_url: str | None = None,
        max_requests: int | None = None,
        custom_response_mode: str | None = None,
        custom_response_body: str | None = None,
        custom_response_status: int | None = None,
        custom_response_content_type: str | None = None,
        signing_secret: str | None = None,
        signing_provider: str | None = None,
    ) -> dict[str, Any]:
        """Create or update channel configuration."""
        now = utc_now_iso()
        async with self._db.connection() as conn:
            sel_query = """
                SELECT channel_id, name, auto_forward_url, max_requests,
                       custom_response_mode, custom_response_body,
                       custom_response_status, custom_response_content_type,
                       signing_secret, signing_provider,
                       created_at
                FROM channels
                WHERE channel_id = ?;
            """
            async with conn.execute(sel_query, (channel_id,)) as cursor:
                existing = await cursor.fetchone()

            if existing:
                new_name = name if name is not None else existing["name"]
                new_auto_forward = (
                    auto_forward_url
                    if auto_forward_url is not None
                    else existing["auto_forward_url"]
                )
                new_max_req = (
                    max_requests if max_requests is not None else (existing["max_requests"] or 500)
                )
                new_resp_mode = (
                    custom_response_mode
                    if custom_response_mode is not None
                    else (existing["custom_response_mode"] or "default")
                )
                new_resp_body = (
                    custom_response_body
                    if custom_response_body is not None
                    else existing["custom_response_body"]
                )
                new_resp_status = (
                    custom_response_status
                    if custom_response_status is not None
                    else (existing["custom_response_status"] or 200)
                )
                new_resp_content_type = (
                    custom_response_content_type
                    if custom_response_content_type is not None
                    else (existing["custom_response_content_type"] or "application/json")
                )
                new_sig_secret = (
                    signing_secret
                    if signing_secret is not None
                    else existing["signing_secret"]
                )
                new_sig_provider = (
                    signing_provider
                    if signing_provider is not None
                    else existing["signing_provider"]
                )

                await conn.execute(
                    """
                    UPDATE channels
                    SET name = ?, auto_forward_url = ?, max_requests = ?,
                        custom_response_mode = ?, custom_response_body = ?,
                        custom_response_status = ?, custom_response_content_type = ?,
                        signing_secret = ?, signing_provider = ?,
                        updated_at = ?
                    WHERE channel_id = ?;
                    """,
                    (
                        new_name,
                        new_auto_forward,
                        new_max_req,
                        new_resp_mode,
                        new_resp_body,
                        new_resp_status,
                        new_resp_content_type,
                        new_sig_secret,
                        new_sig_provider,
                        now,
                        channel_id,
                    ),
                )
                created_at = existing["created_at"]
            else:
                new_name = name
                new_auto_forward = auto_forward_url
                new_max_req = max_requests if max_requests is not None else 500
                new_resp_mode = custom_response_mode or "default"
                new_resp_body = custom_response_body
                new_resp_status = custom_response_status or 200
                new_resp_content_type = custom_response_content_type or "application/json"
                new_sig_secret = signing_secret
                new_sig_provider = signing_provider
                created_at = now
                await conn.execute(
                    """
                    INSERT INTO channels (
                        channel_id, name, auto_forward_url, max_requests,
                        custom_response_mode, custom_response_body,
                        custom_response_status, custom_response_content_type,
                        signing_secret, signing_provider,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        channel_id,
                        new_name,
                        new_auto_forward,
                        new_max_req,
                        new_resp_mode,
                        new_resp_body,
                        new_resp_status,
                        new_resp_content_type,
                        new_sig_secret,
                        new_sig_provider,
                        created_at,
                        now,
                    ),
                )
            await conn.commit()

        return {
            "channel_id": channel_id,
            "name": new_name,
            "auto_forward_url": new_auto_forward,
            "max_requests": new_max_req,
            "custom_response_mode": new_resp_mode,
            "custom_response_body": new_resp_body,
            "custom_response_status": new_resp_status,
            "custom_response_content_type": new_resp_content_type,
            "signing_secret": new_sig_secret,
            "signing_provider": new_sig_provider,
            "created_at": created_at,
            "updated_at": now,
        }
