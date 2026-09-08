# Webhook Provider Guides

This guide shows how to route and test webhooks from common providers into `hook-trap`.

## Stripe

Stripe webhooks carry a signature header named `Stripe-Signature` composed of a timestamp (`t=...`) and an HMAC-SHA256 signature (`v1=...`).

### Forwarding Stripe CLI events

If you use the Stripe CLI, forward events directly to your `hook-trap` channel:

```bash
stripe listen --forward-to http://localhost:8080/catch/stripe_test
```

### Triggering test events

```bash
stripe trigger payment_intent.succeeded
```

### Verifying Stripe signatures in hook-trap

1. In the `hook-trap` dashboard, select the incoming Stripe event.
2. Click the **Signature Inspector** tab.
3. The provider will automatically select **Stripe** and fill in the `Stripe-Signature` value.
4. Paste your webhook signing secret (format: `whsec_...`) from Stripe dashboard or CLI output.
5. Click **Check Signature** to confirm whether the signature matches the raw body.

---

## GitHub

GitHub webhooks include event headers and an HMAC signature header:
- `X-GitHub-Event`: Event name (for example, `push`, `pull_request`, `issues`).
- `X-Hub-Signature-256`: Hexadecimal SHA256 HMAC prefixed with `sha256=`.

### Configuring GitHub webhooks

1. In your repository settings on GitHub, navigate to **Settings > Webhooks > Add webhook**.
2. **Payload URL**: `https://<your-public-url>/catch/gh_events` (or a local address if using a tunnel or testing on the same network).
3. **Content type**: Choose `application/json`.
4. **Secret**: Enter a shared secret key.
5. Select the events you want to receive and click **Add webhook**.

### Simulating a GitHub webhook locally

You can simulate a GitHub push event using cURL:

```bash
BODY='{"ref":"refs/heads/main","repository":{"full_name":"octocat/Hello-World"}}'
SECRET="my_github_secret"
SIG=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "$SECRET" | sed 's/^.* //')

curl -X POST http://localhost:8080/catch/gh_events \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: push" \
  -H "X-Hub-Signature-256: sha256=$SIG" \
  -d "$BODY"
```

---

## Shopify

Shopify sends HMAC-SHA256 signatures encoded in base64 within the `X-Shopify-Hmac-Sha256` header.

### Simulating a Shopify order creation

```bash
BODY='{"id": 8209829119461, "email": "buyer@example.com", "total_price": "149.00"}'
SECRET="shopify_shared_secret"
SIG=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "$SECRET" -binary | base64)

curl -X POST http://localhost:8080/catch/shopify_test \
  -H "Content-Type: application/json" \
  -H "X-Shopify-Topic: orders/create" \
  -H "X-Shopify-Hmac-Sha256: $SIG" \
  -d "$BODY"
```

---

## Generic Providers & Custom Webhooks

For custom webhook implementations using HMAC-SHA256 or token authentication:

1. Post any payload to `/catch/{channel_id}`.
2. Verify headers under the **Headers** tab.
3. In the top replay bar, enter your local handler URL (such as `http://localhost:3000/api/webhook`) and click **Replay**.
4. The dashboard records the local server response code and round-trip latency.
