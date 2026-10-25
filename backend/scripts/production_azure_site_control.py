"""Guarded status, stop, and rollback-start for only Azure App Service intermind-api."""

from __future__ import annotations

import argparse
import logging
import time

import requests
from azure.identity import InteractiveBrowserCredential

logging.disable(logging.CRITICAL)

SUBSCRIPTION = "a28b5169-612e-41fb-9549-1bf540bbe43a"
GROUP = "intermind-rg"
SITE = "intermind-api"
RESOURCE_ID = (
    f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{GROUP}"
    f"/providers/Microsoft.Web/sites/{SITE}"
)
BASE = "https://management.azure.com" + RESOURCE_ID
VERSION = "api-version=2025-05-01"


class Stop(RuntimeError):
    """Fixed non-sensitive failure."""


def request(method: str, suffix: str, token: str) -> requests.Response:
    return requests.request(
        method,
        BASE + suffix + ("&" if "?" in suffix else "?") + VERSION,
        headers={"Authorization": "Bearer " + token},
        timeout=30,
    )


def state(token: str) -> str:
    response = request("GET", "", token)
    if response.status_code != 200:
        raise Stop("exact Azure App Service metadata lookup failed")
    data = response.json()
    if (
        data.get("id", "").lower() != RESOURCE_ID.lower()
        or data.get("name", "").lower() != SITE
        or data.get("location", "").lower().replace(" ", "") != "uaenorth"
    ):
        raise Stop("Azure App Service resource identity mismatch")
    value = data.get("properties", {}).get("state", "")
    if value not in {"Running", "Stopped"}:
        raise Stop("Azure App Service state is unexpected")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--status", action="store_true")
    group.add_argument("--stop", action="store_true")
    group.add_argument("--start", action="store_true")
    args = parser.parse_args()
    with InteractiveBrowserCredential(
        tenant_id="AliyahAlabdali24gmail.onmicrosoft.com"
    ) as credential:
        token = credential.get_token("https://management.azure.com/.default").token
        before = state(token)
        if args.status:
            print("PASS: exact Azure App Service state=" + before)
            return
        expected = "Running" if args.stop else "Stopped"
        target = "Stopped" if args.stop else "Running"
        if before != expected:
            raise Stop("Azure App Service was not in required prior state")
        action = "stop" if args.stop else "start"
        response = request("POST", "/" + action, token)
        if response.status_code not in {200, 202, 204}:
            raise Stop("Azure App Service " + action + " operation failed")
        for _ in range(30):
            if state(token) == target:
                print("PASS: exact Azure App Service state=" + target)
                return
            time.sleep(2)
        raise Stop("Azure App Service " + action + " state not confirmed")


if __name__ == "__main__":
    try:
        main()
    except Stop as exc:
        print("STOP: " + str(exc))
        raise SystemExit(1) from None
    except Exception as exc:
        print("STOP: " + type(exc).__name__)
        raise SystemExit(1) from None
