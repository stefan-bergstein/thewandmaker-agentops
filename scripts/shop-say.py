#!/usr/bin/env python3
"""Talk to the real shop from the command line (for rehearsals and the night run).

  scripts/shop-say.py first-year "I'd like a wand suited to charms."
  scripts/shop-say.py --session t1 first-year "..."   # its own conversation
  scripts/shop-say.py --decline            # Mr Ollivander declines the newest pending request
  scripts/shop-say.py --reset              # new day on the desk

The shop address and the desk key come from the cluster (the current oc context); the key is never printed.
"""
from _oc import oc_out
import json, os, subprocess, sys, urllib.request
# Honor the caller's current oc context, including an exported KUBECONFIG.

def oc(*a):
    return oc_out(a).strip()

host = oc("get", "route", "shop", "-n", "ollivanders", "-o", "jsonpath={.spec.host}")
base = "https://" + host

def desk_key():
    return oc("extract", "secret/shop-tokens", "-n", "ollivanders", "--keys=desk", "--to=-")

def call(path, body=None, key=None, method=None):
    h = {"Content-Type": "application/json"}
    if key:
        h["x-desk-token"] = key
    req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers=h, method=method or ("POST" if body is not None else "GET"))
    with urllib.request.urlopen(req, timeout=260) as r:
        return json.loads(r.read())

if sys.argv[1] == "--decline" or sys.argv[1] == "--approve":
    k = desk_key()
    pending = [q for q in call("/api/desk", key=k)["requests"] if q["status"] == "pending"]
    if not pending:
        print("nothing pending"); sys.exit(0)
    q = pending[-1]
    print(call(f"/api/desk/requests/{q['id']}", {"decision": sys.argv[1][2:]}, key=k))
elif sys.argv[1] == "--reset":
    print(call("/api/reset", {}, key=desk_key()))
else:
    # --session NAME: a conversation of its own (like a fresh chat page). Without it, every call for
    # the same customer kind continues one conversation, as before.
    session = None
    if sys.argv[1] == "--session":
        session, sys.argv[1:3] = sys.argv[2], []
    who, text = sys.argv[1], " ".join(sys.argv[2:])
    body = {"who": who, "text": text}
    if session:
        body["session"] = session
    r = call("/api/chat", body)
    print(f"[{r.get('seconds')} s] tools={r.get('tools')} denied={r.get('denied')}\n{r.get('reply')}")
