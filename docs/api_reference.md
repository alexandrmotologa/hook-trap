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

Executes an HTTP replay of a stored webhook request to a destination URL, optionally recalculating fresh HMAC signatures.

- **Route**: `POST /api/channels/{channel_id}/requests/{request_id}/replay`
- **Request body**:

```json
{
  "target_url": "http://localhost:3000/api/webhook",
  "re_sign": true,
  "signing_provider": "stripe",
  "signing_secret": "whsec_live_example"
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

### Burst Concurrency & Race Condition Runner

Dispatches multiple concurrent replays of a webhook request using `asyncio.gather` and semaphores to assess idempotency, double-spending vulnerabilities, and race conditions.

- **Route**: `POST /api/channels/{channel_id}/requests/{request_id}/burst`
- **Request body**:

```json
{
  "target_url": "http://localhost:3000/api/webhook",
  "count": 5,
  "concurrency": 5,
  "re_sign": true,
  "signing_provider": "stripe",
  "signing_secret": "whsec_test_secret"
}
```

#### Response

```json
{
  "target_url": "http://localhost:3000/api/webhook",
  "total": 5,
  "success_count": 1,
  "error_count": 4,
  "avg_latency_ms": 14.8,
  "status_distribution": { "200": 1, "409": 4 },
  "idempotency_verdict": "IDEMPOTENT_HANDLED",
  "results": [
    {
      "iteration": 1,
      "status_code": 200,
      "latency_ms": 12.4,
      "response_snippet": "{\"processed\": true}",
      "error": null
    },
    {
      "iteration": 2,
      "status_code": 409,
      "latency_ms": 14.1,
      "response_snippet": "{\"error\": \"Duplicate event detected\"}",
      "error": null
    }
  ]
}
```

### Get Channel Configuration

Retrieves persisted configuration for a channel, including responder modes and signing secrets.

- **Route**: `GET /api/channels/{channel_id}/config`

#### Response

```json
{
  "channel_id": "a1b2c3d4",
  "name": "Local Checkout Testing",
  "auto_forward_url": "http://localhost:3000/api/webhook",
  "max_requests": 500,
  "custom_response_mode": "echo_challenge",
  "custom_response_body": null,
  "custom_response_status": 200,
  "custom_response_content_type": null,
  "signing_secret": "whsec_my_secret",
  "signing_provider": "stripe",
  "created_at": "2026-09-09T00:00:00Z",
  "updated_at": "2026-09-09T00:15:00Z"
}
```

### Update Channel Configuration

Updates automatic forwarding, request retention, dynamic response handshake modes, and signing defaults for a channel.

- **Route**: `PUT /api/channels/{channel_id}/config`
- **Request body**:

```json
{
  "name": "Local Checkout Testing",
  "auto_forward_url": "http://localhost:3000/api/webhook",
  "max_requests": 500,
  "custom_response_mode": "echo_challenge",
  "custom_response_body": null,
  "custom_response_status": 200,
  "signing_secret": "whsec_my_secret",
  "signing_provider": "stripe"
}
```

### Export Channel Collection

Exports all stored webhooks for a channel in Postman v2.1, Bruno, or JSON format.

- **Route**: `GET /api/channels/{channel_id}/export`
- **Query parameters**:
  - `format` (string, optional, default: `postman`): Export format (`postman`, `bruno`, `json`).

#### Response

Returns JSON with attachment download headers (`Content-Disposition: attachment; filename="..."`).

### Get System Status

Returns server runtime information, including active public tunnel URL if configured.

- **Route**: `GET /api/system/status`

#### Response

```json
{
  "version": "0.1.0",
  "host": "127.0.0.1",
  "port": 8080,
  "public_tunnel_url": "https://random-subdomain.trycloudflare.com"
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

## Workflow Scenarios & Sequence Runner Endpoints

### List Channel Scenarios

Lists all configured multi-step workflow scenarios for a channel.

- **Route**: `GET /api/scenarios?channel_id={channel_id}`

#### Response

```json
[
  {
    "id": "scn_550e8400-e29b-41d4-a716-446655440000",
    "channel_id": "a1b2c3d4",
    "name": "Order Checkout Sequence",
    "description": "Tests full customer creation and charge sequence",
    "created_at": "2026-09-17T15:00:00Z",
    "updated_at": "2026-09-17T15:00:00Z",
    "steps": [
      {
        "id": "step_770e8400-e29b-41d4-a716-446655440000",
        "scenario_id": "scn_550e8400-e29b-41d4-a716-446655440000",
        "step_order": 1,
        "name": "1. customer.created",
        "method": "POST",
        "path_suffix": "/v1/events",
        "headers": { "content-type": "application/json" },
        "body_raw": "{\"type\":\"customer.created\"}",
        "expected_status": 200,
        "delay_ms": 100,
        "created_at": "2026-09-17T15:00:00Z"
      }
    ]
  }
]
```

### Create Scenario

Creates a new workflow scenario.

- **Route**: `POST /api/scenarios`
- **Request body**:

```json
{
  "channel_id": "a1b2c3d4",
  "name": "Order Checkout Sequence",
  "description": "Tests customer creation and charge sequence"
}
```

### Get Scenario Details

- **Route**: `GET /api/scenarios/{scenario_id}`

### Update Scenario

- **Route**: `PUT /api/scenarios/{scenario_id}`
- **Request body**:

```json
{
  "name": "Updated Scenario Name",
  "description": "Updated description"
}
```

### Delete Scenario

Deletes a scenario and all its associated steps.

- **Route**: `DELETE /api/scenarios/{scenario_id}`

### Add Scenario Step

Appends a new step to the scenario.

- **Route**: `POST /api/scenarios/{scenario_id}/steps`
- **Request body**:

```json
{
  "name": "2. payment_intent.succeeded",
  "method": "POST",
  "path_suffix": "/v1/events",
  "headers": { "content-type": "application/json" },
  "body_raw": "{\"type\":\"payment_intent.succeeded\",\"amount\":2000}",
  "expected_status": 200,
  "delay_ms": 250
}
```

### Delete Scenario Step

- **Route**: `DELETE /api/scenarios/{scenario_id}/steps/{step_id}`

### Run Scenario Sequence

Executes all steps in sequential order against a target destination URL, enforcing delays and status assertions.

- **Route**: `POST /api/scenarios/{scenario_id}/run`
- **Request body**:

```json
{
  "target_url": "http://localhost:3000/api/webhook"
}
```

#### Response

```json
{
  "scenario_id": "scn_550e8400-e29b-41d4-a716-446655440000",
  "name": "Order Checkout Sequence",
  "target_url": "http://localhost:3000/api/webhook",
  "success": true,
  "total_steps": 2,
  "passed_steps": 2,
  "failed_steps": 0,
  "total_duration_ms": 385.2,
  "step_results": [
    {
      "step_id": "step_770e8400-e29b-41d4-a716-446655440000",
      "step_order": 1,
      "name": "1. customer.created",
      "target_url": "http://localhost:3000/api/webhook/v1/events",
      "status_code": 200,
      "expected_status": 200,
      "passed": true,
      "latency_ms": 22.4,
      "error": null,
      "response_body_preview": "{\"status\":\"ok\"}"
    }
  ]
}
```

---

## Payload Fuzzing & Mutation Testing Endpoints

### Run Fuzzing on Stored Request

Generates mutations for a captured webhook request and replays each mutated payload against the target URL.

- **Route**: `POST /api/channels/{channel_id}/requests/{request_id}/fuzz`
- **Request body**:

```json
{
  "target_url": "http://localhost:3000/api/webhook",
  "mutate_missing_key": true,
  "mutate_null_injection": true,
  "mutate_type_confusion": true,
  "mutate_corrupted_signature": true,
  "mutate_malformed_json": true
}
```

#### Response

```json
{
  "target_url": "http://localhost:3000/api/webhook",
  "total_cases": 5,
  "passed_count": 4,
  "vulnerable_count": 0,
  "accepted_count": 1,
  "overall_grade": "PASSED",
  "results": [
    {
      "mutation_type": "missing_key",
      "description": "Omit field 'id'",
      "target_url": "http://localhost:3000/api/webhook",
      "status_code": 400,
      "latency_ms": 15.2,
      "resilience_grade": "PASSED",
      "error": null,
      "payload_preview": "{\"event\":\"payment_intent.succeeded\"}"
    }
  ]
}
```

### Run Custom Fuzz Suite

Runs custom mutation test cases against a target URL.

- **Route**: `POST /api/scenarios/fuzz/run`
- **Request body**:

```json
{
  "target_url": "http://localhost:3000/api/webhook",
  "channel_id": "a1b2c3d4",
  "cases": [
    {
      "mutation_type": "malformed_json",
      "description": "Syntax error test",
      "method": "POST",
      "path_suffix": "",
      "headers": { "content-type": "application/json" },
      "body_raw": "{invalid json syntax"
    }
  ]
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

### Event: `scenario_run_started`

Dispatched when a sequence scenario begins running:

```json
{
  "event": "scenario_run_started",
  "data": {
    "scenario_id": "scn_550e8400-e29b-41d4-a716-446655440000",
    "name": "Order Checkout Sequence",
    "total_steps": 3,
    "target_url": "http://localhost:3000/api/webhook"
  }
}
```

### Event: `scenario_step_completed`

Dispatched when an individual scenario step finishes execution:

```json
{
  "event": "scenario_step_completed",
  "data": {
    "scenario_id": "scn_550e8400-e29b-41d4-a716-446655440000",
    "step_id": "step_770e8400-e29b-41d4-a716-446655440000",
    "step_order": 1,
    "name": "1. customer.created",
    "status_code": 200,
    "expected_status": 200,
    "passed": true,
    "latency_ms": 25.3,
    "error": null
  }
}
```

### Event: `scenario_run_completed`

Dispatched when the complete scenario run finishes:

```json
{
  "event": "scenario_run_completed",
  "data": {
    "scenario_id": "scn_550e8400-e29b-41d4-a716-446655440000",
    "success": true,
    "passed_steps": 3,
    "failed_steps": 0,
    "total_duration_ms": 420.5
  }
}
```

### Keepalive

The server sends `{"event": "ping"}` if no messages are exchanged for 30 seconds. The client can reply with plain string `"pong"`. If the client sends `"ping"`, the server replies with `"pong"`.
