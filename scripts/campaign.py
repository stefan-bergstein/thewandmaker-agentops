#!/usr/bin/env python3
"""Run the second oracle's campaign against one or more releases of the rails, one after the other.

  scripts/campaign.py 1.5 1.5.1

Each campaign runs inside shop-front against the real apprentice and lands in MLflow
(experiment "red-team"). The deck's campaign slide replays the newest run per release.
"""
from _oc import oc_out
import json
import subprocess
import sys
import time
import urllib.request
import os
# Honor the caller's current oc context, including an exported KUBECONFIG.


def oc(*a):
    return oc_out(a).strip()


def main():
    host = oc("get", "route", "shop", "-n", "ollivanders", "-o", "jsonpath={.spec.host}")
    key = oc("extract", "secret/shop-tokens", "-n", "ollivanders", "--keys=desk", "--to=-")
    h = {"x-desk-token": key, "Content-Type": "application/json"}
    for rel in sys.argv[1:] or ["1.5", "1.5.1"]:
        req = urllib.request.Request(f"https://{host}/api/campaign/run", data=json.dumps({"release": rel}).encode(),
                                     headers=h, method="POST")
        print(rel, urllib.request.urlopen(req, timeout=60).read().decode(), flush=True)
        while True:
            time.sleep(15)
            d = json.loads(urllib.request.urlopen(urllib.request.Request(
                f"https://{host}/api/campaign?release={rel}", headers=h), timeout=60).read())
            r = d["runs"].get(rel) or {}
            print(f"  {len(r.get('feed', []))}/{r.get('total', '?')}", flush=True)
            if not d["running"]:
                break
        rules = {k: f"{v['held']}/{v['total']}" for k, v in r.get("rules", {}).items()}
        print(f"  release {rel}: {rules} served {r.get('served')} -> {'may ship' if r.get('gate', {}).get('ship') else 'blocked'}"
              f" (MLflow run {r.get('mlflow_run', r.get('mlflow_error'))})", flush=True)


if __name__ == "__main__":
    main()
