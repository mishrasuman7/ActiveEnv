// The demo scenario: a config that looks perfect but hides two silent failures
// (a test Stripe key in prod, and a staging DB in prod) plus one healthy key.

export const EXAMPLE_CONFIG = `# production.env — "this passed every check"
DATABASE_URL=postgres://app:s3cr3t@staging-db.internal:5432/app_staging
STRIPE_SECRET_KEY=sk_test_demoNotARealKey123
GITHUB_TOKEN=ghp_demoNotARealToken123
DJANGO_DEBUG=False
`;

export const EXAMPLE_FILES: Record<string, string> = {
  "app/billing.py": `import os
import stripe


def charge_customer(customer_id, amount_cents):
    """Charge a real customer for their subscription."""
    stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
    return stripe.Charge.create(
        customer=customer_id,
        amount=amount_cents,
        currency="usd",
    )
`,
  "app/db.py": `from django.conf import settings
from sqlalchemy import create_engine


def get_engine():
    # Primary application database for production traffic.
    return create_engine(settings.DATABASE_URL)
`,
  "app/ci.py": `import os
import httpx


def trigger_deploy():
    token = os.environ["GITHUB_TOKEN"]
    return httpx.post(
        "https://api.github.com/repos/acme/app/deployments",
        headers={"Authorization": f"Bearer {token}"},
    )
`,
};

// Suggested corrected values shown as placeholders in the approve box.
export const SUGGESTED_FIX: Record<string, string> = {
  STRIPE_SECRET_KEY: "sk_live_demoNotARealKey123",
  DATABASE_URL: "postgres://app:s3cr3t@prod-db.internal:5432/app_production",
  GITHUB_TOKEN: "ghp_demoCorrectAccount123",
};
