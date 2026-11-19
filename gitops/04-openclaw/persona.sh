#!/usr/bin/env bash
# With a connected OpenShell CLI: give running apprentices the persona files from this folder (AGENTS.md, SOUL.md,
# IDENTITY.md, USER.md) without recreating them. Recreating a sandbox empties its audit log; this
# only rewrites four files in the workspace. OpenClaw reads them when a conversation starts, so
# new conversations have the new persona and nothing is restarted.
#
#   bash persona.sh                          # every apprentice
#   APPRENTICE_NAME=apprentice-3 bash persona.sh   # one of them, to try it first
#
# The old files stay next to the new ones as *.before, once, so a bad persona can be put back.
# After the copy each apprentice answers one question, so you see who he says he is. Idempotent.
set -euo pipefail
cd "$(dirname "$0")"
WS=""
for f in AGENTS.md SOUL.md IDENTITY.md USER.md; do
  WS="$WS [ -f ~/.openclaw/workspace/$f.before ] || cp ~/.openclaw/workspace/$f ~/.openclaw/workspace/$f.before 2>/dev/null || true;"
  WS="$WS echo $(openssl base64 -A -in "$f") | base64 -d > ~/.openclaw/workspace/$f;"
done
ONLY=${APPRENTICE_NAME:-}
for NAME in $(openshell sandbox list | awk '$1 ~ /^apprentice(-[0-9]+)?$/ {print $1}'); do
  [ -z "$ONLY" ] || [ "$ONLY" = "$NAME" ] || continue
  openshell sandbox exec -n "$NAME" --no-tty --timeout 60 -- sh -c "$WS head -1 ~/.openclaw/workspace/AGENTS.md" </dev/null | sed "s/^/$NAME: /"
  openshell sandbox exec -n "$NAME" --no-tty --timeout 180 -- openclaw agent --thinking off --json \
    --session-id "persona-$(date +%s)" \
    --message "[customer: a walk-in] Good day. Who are you, whose shop is this, and what is the shop called?" </dev/null 2>/dev/null |
    python3 -c 'import json,sys
s=sys.stdin.read(); i=s.find("{")
try:
    d=json.loads(s[i:]); r=d.get("result",d); print("   says:", " ".join(p.get("text") or "" for p in r.get("payloads",[])).strip()[:400])
except Exception as e:
    print("   no answer:", e)'
done
