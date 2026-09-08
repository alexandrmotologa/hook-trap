# Architecture

This document describes the structure and runtime data flow of `hook-trap`.

## Overview

`hook-trap` acts as a local proxy between webhook producers (external services, test scripts) and webhook consumers (your local web application). It combines HTTP ingestion, SQLite persistence, WebSocket broadcasting, and an HTTP client forwarder.

```mermaid
flowchart TD
    Producer["Webhook Producer (Stripe, GitHub, cURL)"]
    subgraph HookTrap["hook-trap Core Process"]
        CatchRoute["Universal Ingestion Route (/catch/{channel})"]
        DB[(SQLite WAL Database)]
        WSManager["WebSocket Connection Manager"]
        Forwarder["HTTP Replay / Forward Engine (httpx)"]
    end
    Browser["Inspector UI (Browser Dashboard)"]
    LocalApp["Local Dev Server (http://localhost:3000)"]

    Producer -->|HTTP POST/GET/PUT| CatchRoute
    CatchRoute -->|Store raw payload & headers| DB
    CatchRoute -->|Push new_request event| WSManager
    WSManager -->|WebSocket /ws/{channel}| Browser
    CatchRoute -.->|Optional Auto-Forward| Forwarder
    Browser -->|1-Click Replay POST| Forwarder
    Forwarder -->|HTTP Request with original headers| LocalApp
    LocalApp -->|Response status & body| Forwarder
    Forwarder -->|Record latency & status| DB
    Forwarder -->|Push replay_executed event| WSManager
```

## Core components

### Ingestion layer (`hook_trap/routes/catch.py`)

The catch router accepts all standard HTTP methods (`POST`, `GET`, `PUT`, `PATCH`, `DELETE`, `HEAD`, `OPTIONS`) on `/catch/{channel_id}` and arbitrary subpaths.

Key behaviors:
- Reads the raw body stream using `request.body()` before parsing to prevent signature tampering.
- Captures all request headers into a dictionary, preserving the original casing of security-relevant headers.
- Parses JSON if valid while keeping the original string representation intact for binary or raw verification.
- Inserts the request into SQLite and dispatches a notification through the WebSocket manager.
- If the channel has an auto-forward URL configured, schedules an asynchronous background task to forward the payload.

### Persistence layer (`hook_trap/database.py`)

Data is stored in SQLite using `aiosqlite`. WAL (Write-Ahead Logging) mode is enabled by default to allow concurrent reads and writes without locking.

Three tables are maintained:

1. `webhook_requests`: Stores captured requests.
   - `id`: UUIDv4 primary key.
   - `channel_id`: Identifier for grouping requests. Indexed for fast channel queries.
   - `timestamp`: UTC ISO datetime string. Indexed in descending order.
   - `method`: HTTP method in uppercase.
   - `path`: Request path, including subpaths.
   - `query_params`: JSON string of URL query parameters.
   - `headers`: JSON string of headers received from the caller.
   - `body_raw`: Raw string or base64 encoded binary data.
   - `body_json`: Parsed JSON string when content is valid JSON, otherwise null.
   - `content_type`: Value of the Content-Type header.
   - `client_ip`: Remote IP or `X-Forwarded-For` address.
   - `replay_count`: Number of times this request has been forwarded or replayed.

2. `replay_logs`: Stores outcomes of forward and replay attempts.
   - `id`: UUIDv4 primary key.
   - `request_id`: Foreign key referencing `webhook_requests(id)` with cascading deletion.
   - `target_url`: Target URL where the request was forwarded.
   - `status_code`: HTTP response status code received from the target, or null on network failure.
   - `response_headers`: Headers returned by the target server.
   - `response_body`: Truncated response body (up to 64 KB).
   - `latency_ms`: Round-trip execution time in milliseconds.
   - `created_at`: UTC ISO timestamp.
   - `error`: Error description if the target was unreachable or timed out.

3. `channels`: Persists channel metadata.
   - `channel_id`: Unique channel name or token.
   - `name`: Optional human-readable label.
   - `auto_forward_url`: Target URL to forward requests to automatically.
   - `created_at`: Creation timestamp.
   - `updated_at`: Last update timestamp.

### Real-time streaming (`hook_trap/ws_manager.py` & `hook_trap/routes/websocket.py`)

The `ConnectionManager` class tracks active WebSocket connections grouped by channel ID.

- Multiple browser tabs or tools can connect to the same channel simultaneously.
- When an incoming webhook is stored, `broadcast(channel_id, payload)` sends the event to all subscribers.
- Dead connections are automatically removed on send failure or disconnect.
- The connection keeps alive using periodic 30-second heartbeats.

### Forwarding and replay engine (`hook_trap/forwarder.py`)

The forwarding engine sends captured requests to local or remote endpoints using `httpx.AsyncClient`.

- Header sanitization: Removes host-specific headers (`Host`, `Content-Length`, `Connection`, `Transfer-Encoding`, `Accept-Encoding`) to avoid conflicting with the target connection.
- Signature preservation: Retains original headers such as `Stripe-Signature` or `X-Hub-Signature-256`.
- High-precision timing: Measures round-trip latency using `time.perf_counter()`.
- Error resilience: Catches timeouts, connection refusals, and DNS errors, recording the failure reason in SQLite without crashing the server.

### User interface (`hook_trap/static/`)

The dashboard is delivered as static files (`index.html`, `style.css`, `app.js`) without a build step.

- Dark-themed interface with high contrast.
- Split-pane layout: Ingestion controls and scrollable request list on the left, detailed tabs on the right.
- Live DOM insertion on WebSocket events without requiring full page refreshes.
- Zero external node package dependencies.
