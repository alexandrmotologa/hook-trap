# Command Line Interface Guide

This document describes command line options, environment variables, and configuration practices for `hook-trap`.

## Commands

### `hook-trap serve`

Launches the web server, SQLite persistence engine, and dashboard. Running `hook-trap` without subcommands defaults to `serve`.

```bash
hook-trap serve [OPTIONS]
```

#### Options

| Flag | Shorthand | Type | Default | Description |
|---|---|---|---|---|
| `--port` | `-p` | INTEGER | `8080` | Port to bind the HTTP and WebSocket server |
| `--host` | `-h` | TEXT | `127.0.0.1` | Network host interface |
| `--db-path` | | TEXT | `hook_trap.db` | File path for the SQLite database |
| `--auto-forward` | `-f` | TEXT | `None` | Default URL for automatic forwarding |
| `--tunnel` | `-t` | TEXT | `None` | Start a public HTTPS tunnel (`cloudflare`, `ngrok`, `auto`) |
| `--open-browser` | `-b` | BOOLEAN | `False` | Opens default web browser on launch |
| `--log-level` | | TEXT | `info` | Logging verbosity (`debug`, `info`, `warning`, `error`) |

#### Examples

Run on a custom port with a public Cloudflare tunnel:

```bash
hook-trap serve --port 8080 --tunnel cloudflare
```

Enable auto-forwarding for all incoming requests:

```bash
hook-trap serve --auto-forward http://localhost:3000/api/webhook
```

---

### `hook-trap tail <channel_id>`

Streams incoming webhooks live in your terminal using WebSockets without opening the browser.

```bash
hook-trap tail <channel_id> [OPTIONS]
```

#### Options

| Flag | Shorthand | Type | Default | Description |
|---|---|---|---|---|
| `--host` | `-h` | TEXT | `127.0.0.1` | Server host |
| `--port` | `-p` | INTEGER | `8080` | Server port |
| `--headers` | | BOOLEAN | `False` | Display all request headers in terminal output |
| `--raw` | | BOOLEAN | `False` | Output raw JSON lines |
| `--interactive` | `-i` | BOOLEAN | `True` | Enable interactive keyboard listener for terminal actions |

#### Interactive Terminal Hotkeys (`-i` mode)

When running in interactive mode (`hook-trap tail <channel_id> -i`), single-key terminal shortcuts are enabled:

| Key | Action |
|---|---|
| `r` | Replay the most recently captured webhook to the active target URL |
| `b` | Fire a 5x burst concurrent replay against the active target URL |
| `c` | Clear terminal output console |
| `q` | Gracefully terminate the live tail session |

---

### `hook-trap list <channel_id>`

List captured webhooks stored in the local SQLite database for a specific channel.

```bash
hook-trap list <channel_id> [OPTIONS]
```

#### Options

| Flag | Shorthand | Type | Default | Description |
|---|---|---|---|---|
| `--db-path` | | TEXT | `hook_trap.db` | Path to SQLite database |
| `--limit` | `-n` | INTEGER | `20` | Maximum requests to display |
| `--offset` | | INTEGER | `0` | Records to skip |
| `--method` | `-m` | TEXT | `None` | Filter by HTTP method (POST, GET, etc.) |
| `--search` | `-s` | TEXT | `None` | Filter by substring in path or payload |

#### Example

```bash
hook-trap list stripe_test -n 10 -m POST
```

---

### `hook-trap show <channel_id> <request_id>`

Inspect full details of a captured webhook, including all HTTP headers, raw payload, and replay logs.

```bash
hook-trap show <channel_id> <request_id> [OPTIONS]
```

#### Example

```bash
hook-trap show stripe_test 3Njh4b2eZv
```

---

### `hook-trap replay <channel_id> <request_id>`

Replay a captured webhook to a local or remote target URL directly from the terminal. Supports dynamic HMAC re-signing.

```bash
hook-trap replay <channel_id> <request_id> --target <url> [OPTIONS]
```

#### Options

| Flag | Shorthand | Type | Default | Description |
|---|---|---|---|---|
| `--target` | `-t` | TEXT | *(required)* | Target URL to send the replayed webhook to |
| `--re-sign` | | BOOLEAN | `False` | Recompute fresh HMAC signature headers with current timestamp |
| `--provider` | | TEXT | `None` | Signing provider (`stripe`, `github`, `shopify`, `generic`) |
| `--secret` | | TEXT | `None` | HMAC secret key used for re-signing |
| `--timeout` | | FLOAT | `10.0` | Request timeout in seconds |

#### Example

```bash
hook-trap replay stripe_test 3Njh4b2eZv -t http://localhost:3000/api/webhook --re-sign --provider stripe --secret whsec_test123
```

---

### `hook-trap trigger <channel_id>`

Send a realistic synthetic sample webhook to a channel for rapid testing without needing a third-party service.

```bash
hook-trap trigger <channel_id> [OPTIONS]
```

#### Options

| Flag | Shorthand | Type | Default | Description |
|---|---|---|---|---|
| `--provider` | `-p` | TEXT | `stripe-payment` | Preset: `stripe-payment`, `stripe-checkout`, `github-push`, `github-pr`, `shopify-order`, `slack-challenge`, `custom` |
| `--host` | `-h` | TEXT | `127.0.0.1` | Running server host |
| `--port` | `-p` | INTEGER | `8080` | Running server port |

#### Example

```bash
hook-trap trigger stripe_test --provider github-push
```

---

### `hook-trap export <channel_id>`

Export captured webhooks for a channel to JSON, Postman Collection v2.1, or Bruno collection format.

```bash
hook-trap export <channel_id> [OPTIONS]
```

#### Options

| Flag | Shorthand | Type | Default | Description |
|---|---|---|---|---|
| `--format` | `-f` | TEXT | `json` | Format: `json`, `postman`, or `bruno` |
| `--output` | `-o` | TEXT | `None` | Output file path (prints to terminal if omitted) |

#### Example

```bash
hook-trap export stripe_test --format postman -o stripe_webhooks.json
```

---

### `hook-trap clear <channel_id>`

Delete all captured requests and replay history for a channel.

```bash
hook-trap clear <channel_id> [--force]
```

---

## Environment Variables

All command line options can also be configured via environment variables prefixed with `HOOK_TRAP_`:

| Environment Variable | Equivalent Flag | Default | Description |
|---|---|---|---|
| `HOOK_TRAP_PORT` | `--port` | `8080` | HTTP port |
| `HOOK_TRAP_HOST` | `--host` | `127.0.0.1` | Host address |
| `HOOK_TRAP_DB_PATH` | `--db-path` | `hook_trap.db` | SQLite database file |
| `HOOK_TRAP_DEFAULT_AUTO_FORWARD_URL` | `--auto-forward` | `None` | Default auto-forward URL |
| `HOOK_TRAP_REPLAY_TIMEOUT` | | `10.0` | HTTP replay timeout in seconds |

Variables can be defined in a `.env` file in the project root directory.

---

## Running as a system service (systemd)

To run `hook-trap` persistently on a Linux machine:

```ini
# /etc/systemd/system/hook-trap.service
[Unit]
Description=hook-trap webhook inspector
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/hook-trap
ExecStart=/opt/hook-trap/.venv/bin/hook-trap --host 127.0.0.1 --port 8080 --db-path /var/lib/hook-trap/hook_trap.db
Restart=always

[Install]
WantedBy=multi-user.target
```
