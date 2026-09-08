# API Reference

This document describes the REST endpoints and WebSocket protocols exposed by `hook-trap`.

## Base URLs

- HTTP: `http://localhost:8080`
- WebSocket: `ws://localhost:8080`

Replace `localhost:8080` with your configured host and port.

---

## Ingestion Endpoints

### Catch Webhook

Captures an incoming HTTP request for a given channel.

- **Route**: `ALL /catch/{channel_id}`
- **Route with subpath**: `ALL /catch/{channel_id}/{subpath:path}`
- **Supported methods**: `POST`, `GET`, `PUT`, `PATCH`, `DELETE`, `HEAD`, `OPTIONS`

#### Query parameters

- `status` (integer, optional): Override the HTTP status code returned by `hook-trap` (useful for testing upstream provider retry behavior, for example `?status=500`).

#### Response

- **Status code**: `200 OK` (or custom status code if specified)
- **Content-Type**: `application/json`

```json
{
  "status": "captured",
  "id": "c7a8b4f1-3d2e-4b91-8f5a-71b3e10984cf",
  "channel": "a1b2c3d4",
  "method": "POST",
  "size_bytes": 1024
}
```

---

## Dashboard REST Endpoints

### List Captured Webhooks

Returns paginated webhook records captured for the specified channel.

- **Route**: `GET /api/channels/{channel_id}/requests`
- **Query parameters**:
  - `limit` (integer, default `50`, max `200`): Maximum number of items to return.
  - `offset` (integer, default `0`): Pagination offset.
  - `method` (string, optional): Filter by HTTP method (`POST`, `GET`, etc.).
  - `search` (string, optional): Filter by text in path, headers, or body.

#### Response

```json
{
  "items": [
    {
      "id": "c7a8b4f1-3d2e-4b91-8f5a-71b3e10984cf",
      "channel_id": "a1b2c3d4",
      "timestamp": "2026-09-09T00:30:00Z",
      "method": "POST",
      "path": "/catch/a1b2c3d4/v1/events",
      "content_type": "application/json",
      "client_ip": "127.0.0.1",
      "replay_count": 1,
      "body_size": 256,
      "body_preview": "{\"event\": \"payment_intent.succeeded\"}"
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

### Get Webhook Details

Returns full details for a single captured request, including stored replay attempts.

- **Route**: `GET /api/channels/{channel_id}/requests/{request_id}`

#### Response

```json
{
  "id": "c7a8b4f1-3d2e-4b91-8f5a-71b3e10984cf",
  "channel_id": "a1b2c3d4",
  "timestamp": "2026-09-09T00:30:00Z",
  "method": "POST",
  "path": "/catch/a1b2c3d4/v1/events",
  "query_params": { "source": "stripe" },
  "headers": {
    "host": "localhost:8080",
    "stripe-signature": "t=1600000000,v1=abc123def456",
    "content-type": "application/json"
  },
  "body_raw": "{\"event\": \"payment_intent.succeeded\", \"amount\": 2000}",
  "body_json": { "event": "payment_intent.succeeded", "amount": 2000 },
  "content_type": "application/json",
  "client_ip": "127.0.0.1",
  "replay_count": 1,
  "replays": [
    {
      "id": "8f3b2a1c-99d4-4e2b-b514-6c3f81e0129a",
      "request_id": "c7a8b4f1-3d2e-4b91-8f5a-71b3e10984cf",
      "target_url": "http://localhost:3000/api/webhook",
      "status_code": 200,
      "response_headers": { "content-type": "application/json" },
      "response_body": "{\"received\": true}",
      "latency_ms": 28.4,
      "created_at": "2026-09-09T00:31:10Z",
      "error": null
    }
  ]
}
```

### Clear Channel History

Deletes all requests and replay logs associated with the specified channel.

- **Route**: `DELETE /api/channels/{channel_id}/requests`

#### Response

```json
{
  "status": "cleared",
  "channel_id": "a1b2c3d4",
  "deleted_count": 14
}
```

### Replay Webhook

Executes an HTTP replay of a stored webhook request to a destination URL.

- **Route**: `POST /api/channels/{channel_id}/requests/{request_id}/replay`
- **Request body**:

```json
{
  "target_url": "http://localhost:3000/api/webhook"
}
```

#### Response

```json
{
  "id": "8f3b2a1c-99d4-4e2b-b514-6c3f81e0129a",
  "request_id": "c7a8b4f1-3d2e-4b91-8f5a-71b3e10984cf",
  "target_url": "http://localhost:3000/api/webhook",
  "status_code": 200,
  "response_headers": { "content-type": "application/json" },
  "response_body": "{\"success\": true}",
  "latency_ms": 32.1,
  "error": null
}
```

### Get Channel Configuration

Retrieves persisted configuration for a channel.

- **Route**: `GET /api/channels/{channel_id}/config`

#### Response

```json
{
  "channel_id": "a1b2c3d4",
  "name": "Local Checkout Testing",
  "auto_forward_url": "http://localhost:3000/api/webhook",
  "created_at": "2026-09-09T00:00:00Z",
  "updated_at": "2026-09-09T00:15:00Z"
}
```

### Update Channel Configuration

Updates or configures automatic forwarding for a channel.

- **Route**: `PUT /api/channels/{channel_id}/config`
- **Request body**:

```json
{
  "name": "Local Checkout Testing",
  "auto_forward_url": "http://localhost:3000/api/webhook"
}
```

### Verify Webhook Signature

Validates HMAC signatures against the raw body and a signing secret.

- **Route**: `POST /api/verify-signature`
- **Request body**:

```json
{
  "provider": "stripe",
  "secret": "whsec_test_secret",
  "signature_header": "t=1600000000,v1=52571829f704d4ef01354a35f3ff5e0cffd6...",
  "raw_payload": "{\"event\": \"payment_intent.succeeded\"}"
}
```

Supported providers: `stripe`, `github`, `shopify`, `generic`.

#### Response

```json
{
  "valid": true,
  "message": "Stripe signature matched",
  "details": {
    "computed": "52571829f704d4ef01354a35f3ff5e0cffd6...",
    "provided": "52571829f704d4ef01354a35f3ff5e0cffd6...",
    "timestamp": "1600000000"
  }
}
```

---

## WebSocket Protocol

Connect to the channel stream at:

```
WS /ws/{channel_id}
```

### Connection handshake

Upon connecting, the server sends a greeting:

```json
{
  "event": "connected",
  "channel_id": "a1b2c3d4"
}
```

### Event: `new_request`

Dispatched immediately when a webhook arrives at `/catch/{channel_id}`:

```json
{
  "event": "new_request",
  "data": {
    "id": "c7a8b4f1-3d2e-4b91-8f5a-71b3e10984cf",
    "channel_id": "a1b2c3d4",
    "timestamp": "2026-09-09T00:30:00Z",
    "method": "POST",
    "path": "/catch/a1b2c3d4",
    "headers": {
      "content-type": "application/json",
      "stripe-signature": "t=1600000000,v1=..."
    },
    "body": { "event": "payment_intent.succeeded" },
    "body_size": 340,
    "content_type": "application/json",
    "client_ip": "127.0.0.1"
  }
}
```

### Event: `replay_executed`

Dispatched when a replay completes:

```json
{
  "event": "replay_executed",
  "data": {
    "request_id": "c7a8b4f1-3d2e-4b91-8f5a-71b3e10984cf",
    "replay_id": "8f3b2a1c-99d4-4e2b-b514-6c3f81e0129a",
    "target_url": "http://localhost:3000/api/webhook",
    "status_code": 200,
    "latency_ms": 32.1,
    "error": null
  }
}
```

### Keepalive

The server sends `{"event": "ping"}` if no messages are exchanged for 30 seconds. The client can reply with plain string `"pong"`. If the client sends `"ping"`, the server replies with `"pong"`.
