#!/usr/bin/env bash
# With a connected OpenShell CLI: start a throwaway OpenClaw sandbox on the cluster, run one agent turn through
# inference.local, then try to reach github.com from the sandbox, which the default policy refuses.
set -euo pipefail
TIMEOUT=timeout
if ! command -v timeout >/dev/null; then
  command -v gtimeout >/dev/null || { echo "Install coreutils (timeout or gtimeout required)." >&2; exit 1; }
  TIMEOUT=gtimeout
fi
cd "$(dirname "$0")"
IMG=$(oc get istag openclaw-sandbox:2026.9.5 -n olli-build -o jsonpath='{.image.dockerImageReference}')
CFG=$(openssl base64 -A -in openclaw.json)
"$TIMEOUT" 600 openshell sandbox create --name claw-test --no-keep --from "$IMG" -- sh -c "
mkdir -p ~/.openclaw && echo $CFG | base64 -d > ~/.openclaw/openclaw.json
echo '== turn'
timeout 300 openclaw agent --local --thinking off --session-id smoke --message 'You are the apprentice in Mr Ollivander wand shop. In one sentence: which wood suits a first-year who likes charms?' 2>&1 | grep -v '^\[' | tail -8
# The shop config (tools.profile minimal) gives the agent no shell tool, so we ask the sandbox's
# own shell, which runs under the same policy: 000 means no connection.
echo '== internet from inside the sandbox (should print 000)'
curl -s -m 8 -o /dev/null -w 'github.com: %{http_code}\n' https://github.com || true
"
