#!/usr/bin/env python3
"""Every address of the demo on one page, read from the cluster.

  scripts/links.py                 # the links; the desk key and the password are left out
  scripts/links.py --secrets       # with the desk key in the links
  scripts/links.py --secrets --out local/links.md    # into a file instead of the terminal

`make links` and `make links SECRETS=1` do the same. The output is Markdown, so you can paste it
into a note or a message. With --secrets it holds the desk key, and with that
everything on the cluster: share it the way you would share a password, not in an open channel.
local/ is not in git and not in the deck's zip.
"""
from _oc import oc_out
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def oc(*a):
    return oc_out(a).strip()


def env():
    out = {}
    try:
        for line in open(os.path.join(ROOT, ".env")):
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.rstrip("\n").split("=", 1)
                out[k.strip()] = v.strip()
    except OSError:
        pass
    return out


def main():
    secrets = "--secrets" in sys.argv
    out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else ""
    try:
        console = oc("whoami", "--show-console").rstrip("/")
        shop = "https://" + oc("get", "route", "shop", "-n", "ollivanders", "-o", "jsonpath={.spec.host}")
    except (subprocess.CalledProcessError, FileNotFoundError):
        sys.exit("Not logged in to the cluster. Run: make cluster-login")
    try:
        deck = "https://" + oc("get", "route", "deck", "-n", "ollivanders", "-o", "jsonpath={.spec.host}")
    except subprocess.CalledProcessError:
        deck = "(not deployed: make up-deck)"
    ai = console.replace("console-openshift-console", "rh-ai")
    key = oc("extract", "secret/shop-tokens", "-n", "ollivanders", "--keys=desk", "--to=-") if secrets else "<desk key>"
    e = env()
    ns = console + "/k8s/ns/ollivanders"
    rows = [
        ("The cluster", [
            ("OpenShift console", console, "use your cluster login"),
            ("Topology of the shop", console + "/topology/ns/ollivanders?view=graph", "the link on the first architecture slide"),
            ("The apprentices' pods", console + "/k8s/ns/openshell/pods", "openshell-0 and one pod per sandbox"),
            ("Rails 1.5.1, config map", ns + "/configmaps/rails-1-5-1", "the link on slides 17 and 20"),
            ("Rails 1.5, config map", ns + "/configmaps/rails-1-5", ""),
            ("The rails deployment", ns + "/trustyai.opendatahub.io~v1alpha1~NemoGuardrails/rails", "slide 18"),
            ("OpenShift AI dashboard", ai, ""),
            ("MLflow", ai + "/mlflow", "workspace ollivanders; experiment apprentice (traces), red-team (campaigns)"),
        ]),
        ("The shop, open to everyone", [
            ("Shop chat", shop, "what a customer sees"),
            ("Phone page", shop + "/phone", "what the QR code opens"),
            ("QR code", shop + "/qr.svg", ""),
            ("Rush counters", shop + "/api/rush", "numbers only"),
        ]),
        ("The shop, with the desk key", [
            ("The master's desk", f"{shop}/desk#key={key}", 'requests for the cabinet, "New day"'),
            ("The day's scroll", f"{shop}/scroll#key={key}", "traces and refusals"),
            ("The rails", f"{shop}/rails#key={key}", "guardrail counters"),
            ("The second oracle", f"{shop}/campaign#key={key}", "red-team campaigns"),
        ]),
        ("The deck, served from the cluster", [
            ("The deck, scripted", deck, "open to everyone; nothing in it talks to the cluster"),
            ("The deck, live", deck, "type the password on slide 1 (DECK_PASSWORD in .env; L jumps to the field); the browser remembers you"),
            ("The deck, live, by link", f"{deck}/#key={key}", "the same without typing; slide 1 is the guide, with Prepare and Reset"),
            ("Backstage on its own", f"{shop}/backstage#key={key}", "the same guide and buttons without the deck, also on a phone"),
        ]),
        ("On this laptop", [
            ("The deck from this folder", "deck/index.html", "make deck-live first; keys: N notes, F fullscreen, M live or scripted"),
            ("The apprentice's own console", "http://127.0.0.1:18789", "after: make dashboard"),
            ("OpenShell's terminal UI", "make shell-ui", "slide 12"),
        ]),
    ]
    lines = ["# Operate your agents – safely! Where everything is", ""]
    for title, items in rows:
        lines += [f"## {title}", "", "| What | Where | Note |", "|---|---|---|"]
        lines += [f"| {a} | {b} | {c} |" for a, b, c in items]
        lines.append("")
    lines += ["## Logins", ""]
    lines.append("- OpenShift console, OpenShift AI, MLflow: use your cluster identity provider login")
    if e.get("BASTION_HOST"):
        lines.append(f"- Bastion (the `openshell` CLI lives there): `ssh {e.get('BASTION_USER', 'rosa')}@{e['BASTION_HOST']}`, with your ssh key")
    lines.append("- Renew expired cluster authentication with `oc login` or `make cluster-login`")
    if not secrets:
        lines.append("- The desk key: `make links SECRETS=1` puts it into the links above")
    text = "\n".join(lines) + "\n"
    if out:
        path = os.path.join(ROOT, out)
        with open(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
            f.write(text)
        print("written to", out, "(holds secrets: don't share the file in an open channel)" if secrets else "")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
