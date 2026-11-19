#!/usr/bin/env bash
# With a connected OpenShell CLI: (re)create the long-running "apprentice" sandbox with the shop policy, the
# OpenClaw config (model via inference.local, tools via the tool gateway, spans to the collector)
# and its role, then start OpenClaw's gateway inside it.
#
# Files next to this script: policy.yaml, openclaw.json and the workspace files AGENTS.md,
# SOUL.md, IDENTITY.md, USER.md. OpenClaw's own BOOTSTRAP.md ("birth sequence", asks the
# customer for a name) is removed: it confuses a shop assistant.
#
# Why a gateway: "openclaw agent --local" starts OpenClaw from scratch for every turn (about 20 s
# before the first model call). The gateway stays up in the sandbox, listens on loopback only,
# and "openclaw agent" without --local hands it the turn: 4 to 10 s per answer, several
# customers at once. shop-front restarts it with ~/.openclaw/start-gateway.sh if it is gone.
# openclaw.json sets mcp.sessionIdleTtlMs: OpenClaw keeps one MCP connection alive per conversation
# and refuses new ones at 256 ("live runtime limit"). Every customer, every night visit and every
# campaign attack is a conversation of its own, so without the idle timeout the apprentice stops
# answering after 256 of them (it did, on 15 November). Two idle minutes close a connection now.
# The same gateway serves OpenClaw's Control UI; scripts/dashboard.py reaches it through an
# OpenShell port forward. Favicon fetches and the Discord invite are off: no outbound calls.
#
#   APPRENTICE_NAME=apprentice-2 bash apprentice.sh     # a second one for the rush
set -euo pipefail
TIMEOUT=timeout
if ! command -v timeout >/dev/null; then
  command -v gtimeout >/dev/null || { echo "Install coreutils (timeout or gtimeout required)." >&2; exit 1; }
  TIMEOUT=gtimeout
fi
cd "$(dirname "$0")"
NAME=${APPRENTICE_NAME:-apprentice}
IMG=$(oc get istag openclaw-sandbox:2026.9.5 -n olli-build -o jsonpath='{.image.dockerImageReference}')

openshell sandbox delete "$NAME" >/dev/null 2>&1 && sleep 5 || true
"$TIMEOUT" 300 openshell sandbox create --name "$NAME" --from "$IMG" --policy policy.yaml </dev/null >/dev/null

# A fresh gateway token per sandbox. It only guards the loopback port inside the sandbox.
# The sandbox name goes on the Control UI's top stripe (make dashboard), so you see which one it is.
TOKEN=$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')
CFG=$(sed -e "s/__GATEWAY_TOKEN__/$TOKEN/" -e "s/__APPRENTICE__/$NAME/" openclaw.json | openssl base64 -A)
WS=""
for f in AGENTS.md SOUL.md IDENTITY.md USER.md; do
  WS="$WS echo $(openssl base64 -A -in "$f") | base64 -d > ~/.openclaw/workspace/$f;"
done
START=$(openssl base64 -A <<'SH'
#!/bin/sh
# Start the OpenClaw gateway once; a second call while it runs does nothing.
curl -s -o /dev/null --max-time 2 http://127.0.0.1:18789/ && exit 0
OTEL_BSP_SCHEDULE_DELAY=1000 setsid nohup openclaw gateway run > /tmp/gateway.log 2>&1 < /dev/null &
for i in $(seq 1 90); do
  curl -s -o /dev/null --max-time 2 http://127.0.0.1:18789/ && echo "gateway up after ${i} s" && exit 0
  sleep 1
done
echo "gateway did not start"; tail -20 /tmp/gateway.log; exit 1
SH
)
openshell sandbox exec -n "$NAME" --no-tty -- sh -c "
  mkdir -p ~/.openclaw/workspace ~/.openclaw/state
  # The plugin registry from the image build: it records diagnostics-otel as installed from
  # ClawHub, so OpenClaw trusts it and lets it export spans (see gitops/03-openclaw-image).
  cp /usr/local/lib/olli/.openclaw/state/openclaw.sqlite ~/.openclaw/state/openclaw.sqlite
  cp /usr/local/lib/olli/.openclaw/config-journal-fingerprint.key ~/.openclaw/
  echo $CFG | base64 -d > ~/.openclaw/openclaw.json
  chmod 600 ~/.openclaw/openclaw.json
  $WS
  rm -f ~/.openclaw/workspace/BOOTSTRAP.md
  openclaw mcp add shop --url http://tool-gateway.ollivanders.svc:8080/mcp --transport streamable-http --no-probe >/dev/null
  # Only the shop's tools; the gateway's own discovery tools stay hidden (the policy refuses them anyway).
  openclaw mcp tools shop --include 'shop_*' >/dev/null
  openclaw config validate
  echo $START | base64 -d > ~/.openclaw/start-gateway.sh
  sh ~/.openclaw/start-gateway.sh" </dev/null
openshell sandbox list
