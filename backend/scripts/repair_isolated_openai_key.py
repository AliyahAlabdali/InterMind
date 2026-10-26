"""Validate an operator-supplied OpenAI key and replace only the isolated copy.

The key is entered through a hidden local prompt and stays in process memory.
No key is printed, saved, put in command arguments, or sent to Git. A metadata
GET authenticates it without generating an answer. Azure is never modified.
"""

from __future__ import annotations

import argparse
import getpass
import json
import subprocess
import sys

import requests
from production_runtime_role import VERCEL_PROJECT, VERCEL_SCOPE, vercel_add, vercel_cli


class Stop(RuntimeError):
    """Fixed, non-sensitive failure message."""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set", action="store_true")
    args = parser.parse_args()
    if not args.set:
        raise Stop("--set is required; no value submitted")
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise Stop("visible local terminal required for hidden key input")
    key = getpass.getpass("Current OpenAI project API key (hidden): ")
    if not isinstance(key, str) or not key or any(char.isspace() for char in key):
        raise Stop("OpenAI key absent or malformed; no value submitted")
    response = requests.get(
        "https://api.openai.com/v1/models/gpt-4o-mini",
        headers={"Authorization": "Bearer " + key},
        timeout=20,
    )
    if response.status_code != 200:
        raise Stop(f"OpenAI key model-metadata check HTTP {response.status_code}")
    if response.json().get("id") != "gpt-4o-mini":
        raise Stop("OpenAI model-metadata identity mismatch")
    print("PASS: supplied key authenticates gpt-4o-mini metadata; no inference call")

    result = subprocess.run(
        [vercel_cli(), "project", "inspect", "intermind-api-production", "--scope",
         VERCEL_SCOPE, "--json"],
        capture_output=True, text=True, timeout=40, check=False,
    )
    if result.returncode:
        raise Stop("isolated Vercel backend lookup failed")
    try:
        project = json.loads(result.stdout)
    except ValueError:
        raise Stop("isolated Vercel backend metadata invalid") from None
    if (
        project.get("id") != VERCEL_PROJECT
        or project.get("rootDirectory") != "backend"
        or project.get("owner", {}).get("slug") != VERCEL_SCOPE
    ):
        raise Stop("isolated Vercel backend identity/root/scope mismatch")
    vercel_add("OPENAI_API_KEY", key, secret=True, force=True)
    print("PASS: only isolated backend Production OPENAI_API_KEY replaced; redeploy required")


if __name__ == "__main__":
    try:
        main()
    except Stop as exc:
        print("STOP: " + str(exc))
        raise SystemExit(1) from None
    except Exception as exc:
        print("STOP: " + type(exc).__name__ + "; no secret displayed")
        raise SystemExit(1) from None
