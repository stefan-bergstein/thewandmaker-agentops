#!/usr/bin/env bash
# Build and deploy the shop, then the tool gateway in front of it. Idempotent.
set -euo pipefail
cd "$(dirname "$0")/../.."

oc apply -f gitops/20-shop/00-build.yaml
# Facts live in this namespace, so create it before publishing them.
bash gitops/20-shop/facts.sh

# Random tokens, created once and never written to git or printed.
if ! oc get secret shop-tokens -n ollivanders >/dev/null 2>&1; then
  TOOLS=$(openssl rand -hex 24); DESK=$(openssl rand -hex 24)
  oc create secret generic shop-tokens -n ollivanders --from-literal=tools="$TOOLS" --from-literal=desk="$DESK" >/dev/null
  # The same tools key, in the shape the MCP gateway wants, for the gateway only.
  oc create secret generic shop-tools-credential -n ollivanders --from-literal=token="Bearer $TOOLS" >/dev/null
  oc label secret shop-tools-credential -n ollivanders mcp.kuadrant.io/secret=true >/dev/null
  unset TOOLS DESK
fi

bash scripts/wait-for.sh sa ollivanders builder
oc start-build shop -n ollivanders --from-dir=apps/shop --follow --wait >/dev/null
echo "shop image built"
oc apply -f gitops/20-shop/10-shop-tools.yaml
# The tool gateway needs OpenShift AI's gateway class and the MCP gateway's CRDs (make up-operators,
# make up-openshift-ai). On a fresh cluster they arrive minutes after the subscriptions.
bash scripts/wait-for.sh exists - gatewayclass/data-science-gateway-class
bash scripts/wait-for.sh crd mcpgatewayextensions.mcp.kuadrant.io mcpserverregistrations.mcp.kuadrant.io
oc apply -f gitops/21-tool-gateway/tool-gateway.yaml
bash scripts/wait-for.sh condition ollivanders gateway.gateway.networking.k8s.io/tool-gateway Programmed 600

# The gateway adds the shop's key to every request it routes to shop-tools. credentialRef above
# only covers the broker's own tool discovery; tool calls go through this route. The value comes
# from the secret at install time and is not stored in git.
python3 - <<'PY'
import base64, json, subprocess
tok = json.loads(subprocess.check_output(["oc", "get", "secret", "shop-tokens", "-n", "ollivanders", "-o", "json"]))["data"]["tools"]
tok = base64.b64decode(tok).decode()
patch = [{"op": "add", "path": "/spec/rules/0/filters", "value": [{"type": "RequestHeaderModifier",
          "requestHeaderModifier": {"set": [{"name": "Authorization", "value": "Bearer " + tok}]}}]}]
subprocess.run(["oc", "patch", "httproute", "shop-tools", "-n", "ollivanders", "--type", "json", "-p", json.dumps(patch)],
               check=True, stdout=subprocess.DEVNULL)
print("tool gateway adds the shop key on the shop-tools route")
PY
oc rollout status deploy/shop-tools -n ollivanders --timeout=300s

# model-gateway: upstream is the MaaS base URL from .env (not a secret; the key stays in OpenShell).
# The gateway reads its configmap and secret only at start, so note their versions and restart it
# below if either changed.
gw_conf() { oc get configmap/model-gateway secret/oracle-backup -n ollivanders \
              -o jsonpath='{range .items[*]}{.metadata.resourceVersion} {end}' 2>/dev/null || true; }
before=$(gw_conf)
python3 - <<'PY' | oc apply -f - >/dev/null
import json
env = dict(l.rstrip("\n").split("=", 1) for l in open(".env") if "=" in l and not l.startswith("#"))
base = env["modelendpoint"].split("/chat/completions")[0]
# The second backup: another model endpoint from Red Hat (REDHATTMM_* in .env; the URL and the model
# name are not secrets, the key goes into the secret oracle-backup). Without them it stays off.
val = lambda k: env.get(k, "").strip().strip('"').strip("'")
spare = val("REDHATTMM_BASE_URL").rstrip("/")
if spare and not spare.endswith("/v1"):
    spare += "/v1"
print(json.dumps({"apiVersion": "v1", "kind": "ConfigMap",
                  "metadata": {"name": "model-gateway", "namespace": "ollivanders"},
                  "data": {"MODEL_UPSTREAM": base, "MODEL_THINKING": "false",
                           # the model's name at MaaS (from .env) and what each call to it carries
                           "MODEL_NAME": env["model"].strip(), "MODEL_EXTRA": json.dumps({"reasoning_effort": "low"}),
                           # chapter 3: NeMo Guardrails (gitops/23-guardrails); if it isn't there, the
                           # gateway logs it and lets requests through unchecked.
                           "RAILS_URL": "http://rails.ollivanders.svc", "RAILS_CONFIG": "release-1-5-1",
                           # The backup oracle (OpenRouter): one model, pinned to one provider,
                           # reasoning off (measured: no faster, twice the output tokens, and OpenClaw
                           # doesn't hand reasoning back). The key is in the secret oracle-backup
                           # (backup-oracle.sh). ORACLE_MODE picks the first choice:
                           #   backup-first  OpenRouter first, MaaS when it rests, fails or hits the cap
                           #   overflow      MaaS first, OpenRouter when MaaS is locked or its minute full
                           #   lock          MaaS first, OpenRouter only while MaaS is locked
                           # Max's choice on 15 November, for testing: OpenRouter first.
                           # 17 November, the morning of the talk: the old MaaS key was blocked (401) and
                           # the Red Hat endpoint answered 403. With a new MaaS key and model
                           # (gpt-oss-120b) MaaS is the fallback again: OpenRouter first, MaaS when it
                           # rests, fails or hits its cap.
                           "ORACLE_MODE": "backup-first",
                           "BACKUP_UPSTREAM": "https://openrouter.ai/api/v1",
                           "BACKUP_MODEL": "deepseek/deepseek-v4.1-flash",
                           "BACKUP_REQUEST": json.dumps({"provider": {"order": ["baidu/fp8"], "allow_fallbacks": True},
                                                         "reasoning": {"enabled": False}}),
                           # hard cap on what the key may have spent, US dollars; prices per million tokens
                           "BACKUP_CAP_USD": "0",   # 0: no cap of ours since 17 November; was 3
                           "BACKUP_PRICE_INPUT": "0.0507",
                           "BACKUP_PRICE_OUTPUT": "0.2028", "BACKUP_PRICE_CACHE_READ": "0.001014",
                           # The second backup takes a call when OpenRouter can't (failed, resting,
                           # at its cap). No cap, nobody bills us for it.
                           "SPARE_UPSTREAM": spare, "SPARE_MODEL": val("REDHATTMM_MODEL") if spare else "",
                           "SPARE_NAME": "Red Hat (GLM)",
                           # Of the two backups the Red Hat endpoint is asked first, OpenRouter
                           # second (Max, 16 November). "backup" puts OpenRouter first again.
                           "BACKUP_FIRST": "backup"}}))   # OpenRouter first (Max, 17 November 11:15: the Red Hat endpoints are rate-limited); then GLM, then MaaS
PY
bash gitops/20-shop/backup-oracle.sh
oc apply -f gitops/20-shop/30-model-gateway.yaml
if [ "$before" != "$(gw_conf)" ]; then
  oc rollout status deploy/model-gateway -n ollivanders --timeout=300s >/dev/null
  oc rollout restart deploy/model-gateway -n ollivanders >/dev/null
  echo "model-gateway restarted: its configmap or secret changed"
fi
oc rollout status deploy/model-gateway -n ollivanders --timeout=300s

# shop-front talks to the OpenShell gateway with the CLI's client certificate.
oc get secret openshell-client-tls -n openshell -o json | python3 -c '
import json, sys
s = json.load(sys.stdin)
print(json.dumps({"apiVersion": "v1", "kind": "Secret", "type": s["type"], "data": s["data"],
                  "metadata": {"name": "openshell-client-tls", "namespace": "ollivanders"}}))' | oc apply -f - >/dev/null
# The addresses the backstage page links to, read from this cluster: its console, and where the deck
# is served (gitops/24-deck; the route's host follows the cluster's ingress domain).
links_before=$(oc get configmap shop-links -n ollivanders -o jsonpath='{.metadata.resourceVersion}' 2>/dev/null || true)
oc create configmap shop-links -n ollivanders --dry-run=client -o yaml \
  --from-literal=console="$(oc whoami --show-console)" \
  --from-literal=deck="https://deck-ollivanders.$(oc get ingresses.config/cluster -o jsonpath='{.spec.domain}')" | oc apply -f - >/dev/null
# The hosted deck's password (DECK_PASSWORD in .env): one password lets a browser into the live
# deck. It goes into the secret deck-login and nowhere else; the value is never printed. Without
# the line in .env the secret is left alone and, if there is none, the deck has no password door.
login_before=$(oc get secret deck-login -n ollivanders -o jsonpath='{.metadata.resourceVersion}' 2>/dev/null || true)
python3 scripts/deck-login.py
login_after=$(oc get secret deck-login -n ollivanders -o jsonpath='{.metadata.resourceVersion}' 2>/dev/null || true)
if [ -n "$login_after" ]; then echo "deck password: set (secret deck-login)"; else echo "deck password: none (add DECK_PASSWORD to .env and run this again)"; fi
oc apply -f gitops/20-shop/20-shop-front.yaml
if [ "$login_before" != "$login_after" ]; then
  oc rollout restart deploy/shop-front -n ollivanders >/dev/null
fi
if [ -n "$links_before" ] && [ "$links_before" != "$(oc get configmap shop-links -n ollivanders -o jsonpath='{.metadata.resourceVersion}')" ]; then
  oc rollout restart deploy/shop-front -n ollivanders >/dev/null
fi
oc rollout status deploy/shop-front -n ollivanders --timeout=300s
echo "Shop: https://$(oc get route shop -n ollivanders -o jsonpath='{.spec.host}')"
echo "Desk: the same host + /desk#key=<desk token>   (oc extract secret/shop-tokens -n ollivanders --keys=desk --to=-)"
