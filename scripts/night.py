#!/usr/bin/env python3
"""The blond boy comes back while the shop is shut: a list of tricks against the real apprentice.

Run it the evening before the talk ("make night"). Every visit is a new conversation (session
night-<n>), goes through the real shop front, and lands on the day's scroll under
"while the shop was shut". Two visits at a time; about eight minutes in all.
Run it once: every run adds its visits to what the scroll counts as the night.
"""
from _oc import oc_out
import concurrent.futures
import json
import subprocess
import sys
import time
import urllib.request
import os
# Honor the caller's current oc context, including an exported KUBECONFIG.

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "apps", "shop", "shop"))
from tricks import TRICKS  # noqa: E402  (one list, shared with the shop's backstage page)


def oc(*a):
    return oc_out(a).strip()


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else len(TRICKS)
    base = "https://" + oc("get", "route", "shop", "-n", "ollivanders", "-o", "jsonpath={.spec.host}")
    stamp = time.strftime("%m%d%H%M")

    def visit(i):
        body = {"who": "blond-boy", "text": TRICKS[i % len(TRICKS)], "session": f"night-{stamp}-{i:02d}"}
        req = urllib.request.Request(base + "/api/chat", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=260) as r:
                d = json.loads(r.read())
            mark = "LOCK" if d.get("denied") else "    "
            return f"{i:02d} {mark} {d.get('seconds', '?'):>5} s  {body['text'][:60]:60}  {', '.join(d.get('tools', []))}"
        except Exception as e:  # keep going, the night is long
            return f"{i:02d} FAIL {body['text'][:60]}: {e}"

    # Two at a time. Red Hat MaaS limits tokens per minute; four at a time ran into the limit on
    # 15 November, and every 429 costs a visit a minute of waiting.
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        for line in pool.map(visit, range(n)):
            print(line, flush=True)


if __name__ == "__main__":
    main()
