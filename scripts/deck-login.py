#!/usr/bin/env python3
"""Configure an optional deck password without submitting an empty manifest or exposing the value."""
import base64
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent.parent


def configure(password):
    if not password:
        return
    secret = {"apiVersion": "v1", "kind": "Secret", "type": "Opaque",
              "metadata": {"name": "deck-login", "namespace": "ollivanders"},
              "data": {"password": base64.b64encode(password.encode()).decode()}}
    subprocess.run(["oc", "apply", "-f", "-"], input=json.dumps(secret), text=True,
                   stdout=subprocess.DEVNULL, check=True)


def main():
    values = {}
    for line in (ROOT / ".env").read_text().splitlines():
        name, separator, value = line.partition("=")
        if separator and name.strip() == "DECK_PASSWORD":
            values["DECK_PASSWORD"] = value.strip().strip('"').strip("'")
    configure(values.get("DECK_PASSWORD", ""))


if __name__ == "__main__":
    main()
