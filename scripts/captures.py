#!/usr/bin/env python3
"""Take the captures of real product pages that the deck shows ("make captures").

  mlflow      the newest first-year visit as a trace in MLflow itself, one tool call selected
              (the first-year's on purpose: MLflow shows everything unredacted, and the name must
              not end up on the screen)
  console     the apprentice's own console (OpenClaw's Control UI), with the blond boy's newest
              session open and its tool calls unfolded. It needs the forward and the tunnel, so
              this runs scripts/dashboard.py with a throwaway headless browser; yours is not paired.
  guardrails  the apprentice's rails as the cluster shows them: the NemoGuardrails resource in the
              OpenShift console. The console wants its own login, so a Chrome window opens and you
              log in there yourself, once; pass --no-login to skip it.

Run it after demo 1 has been played once (it needs a first-year visit on the scroll). The pictures
go to deck/assets/img/captures/, and deck/js/captures.js tells the deck when each was taken.
"""
from _oc import oc_out
import json
import os
import subprocess
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = dict(os.environ)


def oc(*a):
    return oc_out(a, env=ENV).strip()


def capture(name, url, *opts):
    subprocess.run(["node", os.path.join(ROOT, "scripts", "capture-ui.mjs"), name, url, *opts], check=True, env=ENV)


def main():
    apps = oc("get", "ingresses.config.openshift.io", "cluster", "-o", "jsonpath={.spec.domain}")
    shop = "https://" + oc("get", "route", "shop", "-n", "ollivanders", "-o", "jsonpath={.spec.host}")
    key = oc("extract", "secret/shop-tokens", "-n", "ollivanders", "--keys=desk", "--to=-")   # never printed
    req = urllib.request.Request(shop + "/api/scroll/traces?limit=200", headers={"x-desk-token": key})
    traces = json.loads(urllib.request.urlopen(req, timeout=60).read())["traces"]
    first = next((t for t in traces if "first-year" in (t.get("customer") or "") and t["status"] == "ok"
                  and not t["session"].startswith(("night-", "redteam-", "phone-"))), None)
    if first:
        mlflow = oc("get", "mlflow", "mlflow", "-o", "jsonpath={.status.url}")
        exp = oc("get", "configmap", "scribe", "-n", "ollivanders", "-o", "jsonpath={.data.experiment_id}")
        capture("mlflow", f"{mlflow}/#/experiments/{exp}/traces?selectedEvaluationId={first['id']}&workspace=ollivanders",
                "--wait", "4000", "--click", "openclaw.tool.execution")
    else:
        print("mlflow: no first-year visit on the scroll yet; play demo 1 once, then run this again")
    subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "dashboard.py"), "apprentice", "--capture",
                    "--click", "~explicit:blond-boy", "--click", "~Used ", "--wait", "4000"], check=False)
    if "--no-login" not in sys.argv:
        capture("guardrails", f"https://console-openshift-console.{apps}/k8s/ns/ollivanders/"
                "trustyai.opendatahub.io~v1alpha1~NemoGuardrails/rails/yaml", "--wait", "6000", "--login")


if __name__ == "__main__":
    main()
