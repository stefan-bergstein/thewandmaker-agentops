#!/usr/bin/env python3
"""The three oracles behind the model gateway: who answers first, and what it has cost.

  scripts/oracle.py                   # calls, tokens and dollars per oracle, the mode
  scripts/oracle.py mode backup-first # OpenRouter first, MaaS as fallback (until the next restart)
  scripts/oracle.py mark              # remember the spend now ...
  scripts/oracle.py since             # ... and show what was spent since the mark

Modes: backup-first, overflow, lock, maas, backup, spare (walkthrough, section 6). "The backup" in a mode
means OpenRouter first and the second backup (REDHATTMM_* in .env) when OpenRouter can't. A mode set here holds
until the model gateway restarts; the lasting one is ORACLE_MODE in gitops/20-shop/install.sh.
Reads the gateway through shop-front (oc exec); no key is read or printed.
"""
from _oc import oc_out
import json
import os
import subprocess
import sys
# Honor the caller's current oc context, including an exported KUBECONFIG.

MARK = os.path.join(os.path.dirname(__file__), "..", "local", "oracle-mark.json")
GW = "http://model-gateway.ollivanders.svc:8080/oracle"


def ask(mode=None):
    code = ("import httpx,json,sys;m=sys.argv[1] if len(sys.argv)>1 else '';"
            f"r=httpx.post('{GW}',json={{'mode':m}}) if m else httpx.get('{GW}');"
            "print(json.dumps(r.json()))")
    out = oc_out(["exec", "deploy/shop-front", "-n", "ollivanders", "--", "python", "-c", code] + ([mode] if mode else []))
    return json.loads(out)


def show(d):
    m, b, s = d["maas"], d["backup"], d.get("spare") or {}
    first = {"backup-first": "OpenRouter first, MaaS as fallback", "overflow": "MaaS first, OpenRouter for the overflow",
             "lock": "MaaS first, OpenRouter only while MaaS is locked", "maas": "MaaS only",
             "backup": "OpenRouter, then the second backup, no MaaS",
             "spare": "the second backup only"}.get(d["mode"], d["mode"])
    if d.get("first") == "spare" and d["mode"] != "maas":
        first += "; of the two backups the second (Red Hat) is asked first"
    print(f"mode           {d['mode']}: {first}")
    print(f"last answer    {d['last']['oracle'] or '-'}")
    print(f"Red Hat MaaS   {m['calls']} calls, {m['tokens']:,} tokens (free for us)")
    print(f"OpenRouter     {b['calls']} calls ({b['failed']} failed), {b['input_tokens']:,} in "
          f"({b['cached_tokens']:,} from the cache), {b['output_tokens']:,} out, "
          f"{b['dollars']:.4f} USD since the gateway started")
    print(f"               the key has spent {b['spent_total']:.4f} USD, " + (f"cap {b['cap']:.2f} USD" if b['cap'] > 0 else "no cap of ours")
          + (" (resting after an error: " + b["last_error"][:80] + ")" if b.get("resting") else ""))
    if s.get("configured"):
        print(f"{s['name']:14} {s['calls']} calls ({s['failed']} failed), {s['input_tokens']:,} in, "
              f"{s['output_tokens']:,} out, model {s['model'].split('/')[-1]}; "
              + ("asked first of the two backups" if d.get("first") == "spare" else "takes over when OpenRouter can't")
              + (" (resting after an error: " + s["last_error"][:80] + ")" if s.get("resting") else ""))
    else:
        print("second backup  not configured (REDHATTMM_* in .env, then make up-shop)")


def main():
    args = sys.argv[1:]
    if args[:1] == ["mode"] and len(args) == 2:
        show(ask(args[1]))
    elif args == ["mark"]:
        d = ask()
        json.dump({"backup_spent": d["backup"]["spent_total"], "backup_calls": d["backup"]["calls"],
                   "maas_calls": d["maas"]["calls"]}, open(MARK, "w"))
        print(f"marked at {d['backup']['spent_total']:.4f} USD")
    elif args == ["since"]:
        d, m = ask(), json.load(open(MARK))
        print(f"since the mark: OpenRouter {d['backup']['calls'] - m['backup_calls']} calls, "
              f"{d['backup']['spent_total'] - m['backup_spent']:.4f} USD; MaaS {d['maas']['calls'] - m['maas_calls']} calls")
        print("(counts since the gateway started; a restart in between makes these numbers wrong)")
    elif not args:
        show(ask())
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
