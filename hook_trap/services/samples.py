from typing import Any

SAMPLE_TEMPLATES: dict[str, dict[str, Any]] = {
    "stripe-payment": {
        "provider": "stripe",
        "description": "Stripe payment_intent.succeeded event",
        "subpath": "v1/events",
        "headers": {
            "Content-Type": "application/json",
            "Stripe-Signature": "t=1690000000,v1=52571829f704d4ef01354a35f3ff5e0cffd6a2",
            "User-Agent": "Stripe/1.0 (+https://stripe.com/docs/webhooks)",
        },
        "body": {
            "id": "evt_3Njh4b2eZvKYlo2C0zXp0001",
            "object": "event",
            "api_version": "2024-06-20",
            "created": 1690000000,
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_3Njh4b2eZvKYlo2C0zXp0001",
                    "object": "payment_intent",
                    "amount": 4900,
                    "amount_received": 4900,
                    "currency": "usd",
                    "customer": "cus_ON8K3P01",
                    "status": "succeeded",
                }
            },
        },
    },
    "stripe-checkout": {
        "provider": "stripe",
        "description": "Stripe checkout.session.completed event",
        "subpath": "v1/events",
        "headers": {
            "Content-Type": "application/json",
            "Stripe-Signature": "t=1690000000,v1=abc99887766554433221100ff",
        },
        "body": {
            "id": "evt_12345checkout",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_a1b2c3",
                    "payment_status": "paid",
                    "customer_email": "jane.doe@example.com",
                    "amount_total": 12500,
                    "currency": "usd",
                }
            },
        },
    },
    "github-push": {
        "provider": "github",
        "description": "GitHub Git push commit event",
        "subpath": "github",
        "headers": {
            "Content-Type": "application/json",
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": "sha256=d8e8fca2dc0f896fd7cb4cb0031ba249",
            "User-Agent": "GitHub-Hookshot/1.0",
        },
        "body": {
            "ref": "refs/heads/main",
            "before": "6113728f27ae82c7b1a12fce9384f8f43f3b8212",
            "after": "0000000000000000000000000000000000000000",
            "repository": {
                "id": 1296269,
                "name": "Hello-World",
                "full_name": "octocat/Hello-World",
                "private": False,
                "owner": {"name": "octocat", "email": "octocat@github.com"},
            },
            "pusher": {"name": "octocat", "email": "octocat@github.com"},
        },
    },
    "github-pr": {
        "provider": "github",
        "description": "GitHub Pull Request opened event",
        "subpath": "github",
        "headers": {
            "Content-Type": "application/json",
            "X-GitHub-Event": "pull_request",
            "X-Hub-Signature-256": "sha256=ef90812347bcfae89012456",
        },
        "body": {
            "action": "opened",
            "number": 42,
            "pull_request": {
                "title": "Improve webhook replay engine latency",
                "user": {"login": "alexandrmotologa"},
                "state": "open",
            },
        },
    },
    "shopify-order": {
        "provider": "shopify",
        "description": "Shopify order creation event",
        "subpath": "shopify",
        "headers": {
            "Content-Type": "application/json",
            "X-Shopify-Topic": "orders/create",
            "X-Shopify-Hmac-Sha256": "WlhqU0Z1aFhOWHlK...",
        },
        "body": {
            "id": 8209829119461,
            "email": "buyer@example.com",
            "total_price": "189.50",
            "currency": "USD",
            "financial_status": "paid",
        },
    },
    "slack-challenge": {
        "provider": "slack",
        "description": "Slack Events API URL verification challenge",
        "subpath": "slack",
        "headers": {"Content-Type": "application/json"},
        "body": {
            "token": "Jhj5dZrVaK7ZwHHjRyZWjbDl",
            "challenge": "3eZbrw1aBm2rZgRNFDxV2595E9CY3gmdALWMmHkvFXO7tYXAYM8P",
            "type": "url_verification",
        },
    },
    "custom": {
        "provider": "custom",
        "description": "Generic JSON custom notification event",
        "subpath": "custom",
        "headers": {"Content-Type": "application/json"},
        "body": {"event": "custom.notification", "timestamp": "2026-11-19T20:00:00Z"},
    },
}


def get_sample_template(key: str) -> dict[str, Any]:
    """Retrieve sample webhook template by key, with fallback to stripe-payment."""
    normalized = key.lower().strip()
    if normalized in SAMPLE_TEMPLATES:
        return SAMPLE_TEMPLATES[normalized]
    # Check prefix or partial match
    for k, v in SAMPLE_TEMPLATES.items():
        if normalized in (k, v.get("provider")):
            return v
    return SAMPLE_TEMPLATES["stripe-payment"]
