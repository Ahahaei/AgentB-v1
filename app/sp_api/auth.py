import os

import httpx


def get_access_token(seller) -> str:
    """Exchange LWA refresh_token for a short-lived access_token."""
    if os.environ.get("SP_API_ENABLED", "false").lower() != "true":
        return "mock_access_token"

    creds = seller.sp_api_credentials
    if creds is None:
        raise ValueError(f"Seller '{seller.id}' has no SP API credentials configured")

    resp = httpx.post(
        "https://api.amazon.com/auth/o2/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": creds.lwa_refresh_token,
            "client_id": creds.lwa_client_id,
            "client_secret": creds.lwa_client_secret,
        },
    )
    resp.raise_for_status()
    return resp.json()["access_token"]
