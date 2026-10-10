"""Minimal official Amazon SP-API catalog search client.

Requires seller/developer approval, LWA refresh token and AWS IAM signing credentials.
No listing, order, purchase or account mutation endpoints are exposed here.
"""
from __future__ import annotations
import os
from typing import Any
from urllib.parse import urlencode

import httpx


class AmazonIntegrationDisabled(RuntimeError):
    pass


def _config() -> dict[str, str]:
    names = {
        "client_id": "AMAZON_SP_API_LWA_CLIENT_ID",
        "client_secret": "AMAZON_SP_API_LWA_CLIENT_SECRET",
        "refresh_token": "AMAZON_SP_API_REFRESH_TOKEN",
        "aws_access_key": "AWS_ACCESS_KEY_ID",
        "aws_secret_key": "AWS_SECRET_ACCESS_KEY",
        "marketplace_id": "AMAZON_SP_API_MARKETPLACE_ID",
        "region": "AMAZON_SP_API_AWS_REGION",
    }
    config = {key: os.getenv(name, "").strip() for key, name in names.items()}
    missing = [names[key] for key, value in config.items() if not value]
    if missing:
        raise AmazonIntegrationDisabled("Missing required Amazon SP-API configuration: " + ", ".join(missing))
    if os.getenv("AMAZON_SP_API_ENABLE_READS", "false").lower() != "true":
        raise AmazonIntegrationDisabled("Amazon SP-API reads are disabled until developer/seller approval and explicit opt-in.")
    return config


def _lwa_access_token(config: dict[str, str]) -> str:
    response = httpx.post(
        "https://api.amazon.com/auth/o2/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": config["refresh_token"],
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
        },
        timeout=20.0,
    )
    response.raise_for_status()
    token = response.json().get("access_token")
    if not isinstance(token, str) or not token:
        raise AmazonIntegrationDisabled("Amazon LWA did not return an access token.")
    return token


def search_catalog(keywords: str, *, page_size: int = 10) -> dict[str, Any]:
    """Read-only catalog search; never treats catalog presence as demand or profitability."""
    config = _config()
    query = keywords.strip()
    if not query or len(query) > 200:
        raise ValueError("keywords must be 1..200 characters.")
    page_size = max(1, min(int(page_size), 20))
    token = _lwa_access_token(config)
    region = config["region"]
    host = os.getenv("AMAZON_SP_API_HOST", "sellingpartnerapi-na.amazon.com").strip()
    if not host or "/" in host:
        raise AmazonIntegrationDisabled("AMAZON_SP_API_HOST must be a hostname.")
    uri = "/catalog/2022-04-01/items"
    params = {
        "keywords": query,
        "marketplaceIds": config["marketplace_id"],
        "pageSize": str(page_size),
        "includedData": "summaries,identifiers,images",
    }
    url = f"https://{host}{uri}?{urlencode(params)}"
    try:
        from botocore.auth import SigV4Auth
        from botocore.awsrequest import AWSRequest
        from botocore.credentials import Credentials
        from botocore.httpsession import URLLib3Session
    except ImportError as exc:
        raise AmazonIntegrationDisabled("Install botocore to sign official SP-API requests.") from exc
    credentials = Credentials(config["aws_access_key"], config["aws_secret_key"], os.getenv("AWS_SESSION_TOKEN"))
    request = AWSRequest(method="GET", url=url, headers={
        "x-amz-access-token": token,
        "host": host,
        "accept": "application/json",
    })
    SigV4Auth(credentials, "execute-api", region).add_auth(request)
    prepared = request.prepare()
    session = URLLib3Session()
    response = session.send(prepared)
    if response.status_code >= 400:
        raise AmazonIntegrationDisabled(f"Amazon SP-API returned HTTP {response.status_code}; verify roles, region, host and authorization.")
    return {
        "provider": "amazon_sp_api",
        "mode": "read_only_catalog",
        "keywords": query,
        "marketplace_id": config["marketplace_id"],
        "items": response.json(),
        "warning": "Catalog results are not a demand signal, offer price guarantee, supplier source, or profit forecast.",
    }
