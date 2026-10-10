"""Read-only Amazon Selling Partner API catalog search.

Requires official SP-API authorization and seller consent. This connector does not place orders,
publish listings, or treat catalog results as evidence of demand or profit.
"""
from __future__ import annotations

import os
from urllib.parse import urlencode
from typing import Any

import httpx


class AmazonNotReady(RuntimeError):
    pass


def search_catalog(keywords: str, limit: int = 10) -> dict[str, Any]:
    required = {
        "AMAZON_SP_API_LWA_CLIENT_ID": os.getenv("AMAZON_SP_API_LWA_CLIENT_ID", ""),
        "AMAZON_SP_API_LWA_CLIENT_SECRET": os.getenv("AMAZON_SP_API_LWA_CLIENT_SECRET", ""),
        "AMAZON_SP_API_REFRESH_TOKEN": os.getenv("AMAZON_SP_API_REFRESH_TOKEN", ""),
        "AMAZON_SP_API_MARKETPLACE_ID": os.getenv("AMAZON_SP_API_MARKETPLACE_ID", ""),
        "AWS_ACCESS_KEY_ID": os.getenv("AWS_ACCESS_KEY_ID", ""),
        "AWS_SECRET_ACCESS_KEY": os.getenv("AWS_SECRET_ACCESS_KEY", ""),
        "AMAZON_SP_API_AWS_REGION": os.getenv("AMAZON_SP_API_AWS_REGION", ""),
    }
    missing = [name for name, value in required.items() if not value.strip()]
    if missing:
        raise AmazonNotReady("Missing approved SP-API settings: " + ", ".join(missing))
    if os.getenv("AMAZON_SP_API_ENABLE_READS", "false").lower() != "true":
        raise AmazonNotReady("Read-only SP-API access is disabled until approval and explicit opt-in.")
    keywords = keywords.strip()
    if not keywords or len(keywords) > 200:
        raise ValueError("keywords must contain 1 to 200 characters.")
    limit = max(1, min(int(limit), 20))
    try:
        from botocore.auth import SigV4Auth
        from botocore.awsrequest import AWSRequest
        from botocore.credentials import Credentials
    except ImportError as exc:
        raise AmazonNotReady("Install the botocore dependency to sign SP-API requests.") from exc

    token_response = httpx.post(
        "https://api.amazon.com/auth/o2/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": required["AMAZON_SP_API_REFRESH_TOKEN"],
            "client_id": required["AMAZON_SP_API_LWA_CLIENT_ID"],
            "client_secret": required["AMAZON_SP_API_LWA_CLIENT_SECRET"],
        },
        timeout=20,
    )
    token_response.raise_for_status()
    access_token = token_response.json().get("access_token")
    if not access_token:
        raise AmazonNotReady("LWA token response did not include access_token.")

    host = os.getenv("AMAZON_SP_API_HOST", "sellingpartnerapi-na.amazon.com").strip()
    if not host or "/" in host:
        raise AmazonNotReady("AMAZON_SP_API_HOST must be a hostname.")
    region = required["AMAZON_SP_API_AWS_REGION"]
    params = urlencode({
        "keywords": keywords,
        "marketplaceIds": required["AMAZON_SP_API_MARKETPLACE_ID"],
        "pageSize": str(limit),
        "includedData": "summaries,identifiers,images",
    })
    url = f"https://{host}/catalog/2022-04-01/items?{params}"
    credentials = Credentials(
        required["AWS_ACCESS_KEY_ID"],
        required["AWS_SECRET_ACCESS_KEY"],
        os.getenv("AWS_SESSION_TOKEN") or None,
    )
    signed = AWSRequest(method="GET", url=url, headers={
        "x-amz-access-token": access_token,
        "accept": "application/json",
    })
    SigV4Auth(credentials, "execute-api", region).add_auth(signed)
    prepared = signed.prepare()
    response = httpx.get(url, headers=dict(prepared.headers), timeout=30)
    if response.status_code >= 400:
        raise AmazonNotReady(f"SP-API returned HTTP {response.status_code}; verify app roles, marketplace and region.")
    return {
        "provider": "amazon_sp_api",
        "mode": "read_only_catalog",
        "currency": "USD",
        "keywords": keywords,
        "marketplace_id": required["AMAZON_SP_API_MARKETPLACE_ID"],
        "items": response.json(),
        "execution_enabled": False,
        "warning": "Catalog matches do not prove demand, buy-box price, supplier availability, or profit.",
    }
