# hook-trap

A lightweight webhook inspector, debugger, and local forwarding proxy built with FastAPI, WebSockets, and SQLite.

When you develop applications that receive webhooks from Stripe, GitHub, Shopify, or Twilio, testing endpoints locally usually requires third party tunnel services or repeated manual requests. `hook-trap` runs locally, receives incoming payloads on isolated channel URLs, logs them in SQLite, streams them in real time over WebSockets to a dark mode dashboard, and replays them to your development server with one click.

## Features

- **Universal ingestion paths**: Send requests using any HTTP method (POST, GET, PUT, PATCH, DELETE) to `/catch/<channel_id>` or nested subpaths like `/catch/<channel_id>/v1/events`.
- **Live WebSocket streaming**: Inspect payloads and headers as they arrive without refreshing the browser.
- **Exact payload and signature retention**: Preserves raw body bytes and headers, including HMAC signatures from Stripe (`Stripe-Signature`), GitHub (`X-Hub-Signature-256`), and Shopify (`X-Shopify-Hmac-Sha256`).
- **HTTP replay engine**: Replay any captured webhook to a local endpoint such as `http://localhost:3000/api/webhook`, recording latency, status codes, and response headers.
- **Automatic forwarding**: Forward incoming webhooks to your local service as soon as they hit the receiver.
- **Built-in signature validator**: Test your webhook signing secrets against incoming headers and raw request bodies directly in the interface.
- **Code export**: Copy captured requests as ready-to-run cURL commands, Python `httpx` scripts, or JavaScript `fetch` calls.
- **Zero build dependencies**: The web inspector uses vanilla JavaScript and CSS served directly by FastAPI. No Node.js or build steps required.

## Quick start

### Prerequisites

Python 3.12 or newer.

### Installation

Clone the repository and install the dependencies:

```bash
git clone https://github.com/alexandrmotologa/hook-trap.git
cd hook-trap
pip install -e .
```

Alternatively, install using `uv`:

```bash
uv pip install -e ".[dev]"
```

### Running the server

Start the server using the command line interface:

```bash
hook-trap --port 8080 --open-browser
```

By default, the server listens on `http://127.0.0.1:8080`.

To automatically forward every incoming webhook to your local development service:

```bash
hook-trap --port 8080 --auto-forward http://localhost:3000/api/webhook
```

## How to use

1. Open `http://localhost:8080` in your browser. The application redirects to a unique channel, for example `http://localhost:8080/c/a1b2c3d4`.
2. Copy the ingestion URL shown in the top left card (`http://localhost:8080/catch/a1b2c3d4`).
3. Point your webhook provider or test script to this URL:

```bash
curl -X POST http://localhost:8080/catch/a1b2c3d4 \
  -H "Content-Type: application/json" \
  -H "X-Custom-Header: value" \
  -d '{"event": "user.created", "user_id": 42}'
```

4. The request appears immediately in the left sidebar. Click it to inspect formatted JSON, exact raw headers, and query parameters.
5. In the top replay bar, enter your local API address (`http://localhost:3000/api/webhook`) and click **Replay** to send the exact request to your local application.

## CLI options

| Option | Shorthand | Default | Description |
|---|---|---|---|
| `--port` | `-p` | `8080` | Port for the HTTP server |
| `--host` | `-h` | `127.0.0.1` | Network interface to bind to |
| `--db-path` | | `hook_trap.db` | File path for the SQLite database |
| `--auto-forward` | `-f` | None | Default target URL for automatic forwarding |
| `--open-browser` | `-b` | `false` | Automatically opens the browser dashboard |
| `--log-level` | | `info` | Uvicorn logging level |

## Testing upstream retries

To test how upstream providers handle failures, you can simulate specific status codes by appending the `status` query parameter to the catch URL:

```bash
# Simulates a 503 Service Unavailable response
curl -X POST "http://localhost:8080/catch/a1b2c3d4?status=503" \
  -H "Content-Type: application/json" \
  -d '{"retry_test": true}'
```

The server stores the payload normally, notifies the dashboard, and returns HTTP 503 to the caller.

## Running with Docker

Build and run using Docker Compose:

```bash
docker compose up --build
```

Or build the image directly:

```bash
docker build -t hook-trap .
docker run -p 8080:8080 -v hook_trap_data:/data hook-trap
```

## Running tests

Run the test suite with pytest:

```bash
pytest -v tests/
```

## Documentation

- [Architecture Guide](docs/architecture.md): Overview of components, database schema, and WebSocket event flow.
- [API Reference](docs/api_reference.md): Specification of REST endpoints and WebSocket events.
- [Webhook Provider Guides](docs/webhook_guides.md): Recipes for testing Stripe, GitHub, Shopify, and Svix webhooks.
- [CLI Guide](docs/cli_guide.md): Command line flags and environment variables.

## License

MIT
