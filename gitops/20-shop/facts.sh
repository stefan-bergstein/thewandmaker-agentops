#!/usr/bin/env bash
# The fixed facts the deck's architecture picture shows under its boxes: versions and names, read
# from the cluster as it is right now and written to the config map platform-facts. shop-front
# gets them as PLATFORM_FACTS and serves them at /api/platform, next to its live counters.
# Idempotent. Run it again after an upgrade ("make up-facts"); "make up-shop" runs it too.
set -euo pipefail
cd "$(dirname "$0")/../.."

FACTS=$(mktemp)
trap 'rm -f "$FACTS"' EXIT
python3 - <<'PY' > "$FACTS"
import json, subprocess

def oc(*a):
    r = subprocess.run(["oc", *a], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""

def csv(namespace, prefix):
    """Version of an installed operator, from its ClusterServiceVersion."""
    try:
        items = json.loads(oc("get", "csv", "-n", namespace, "-o", "json") or "{}").get("items", [])
    except ValueError:
        return ""
    return next((i["spec"].get("version", "") for i in items if i["metadata"]["name"].startswith(prefix)), "")

def tag(image):
    return image.rsplit(":", 1)[1] if ":" in image.rsplit("/", 1)[-1] else ""

env = dict(l.rstrip("\n").split("=", 1) for l in open(".env") if "=" in l and not l.lstrip().startswith("#"))
openshell = tag(oc("get", "statefulset", "openshell", "-n", "openshell", "-o",
                   "jsonpath={.spec.template.spec.containers[0].image}")).lstrip("v").split("-")[0]
openclaw = next((l.split(":", 1)[1] for l in oc("get", "istag", "-n", "olli-build", "-o", "name").splitlines()
                 if "openclaw-sandbox:" in l), "")
facts = {
    "openshift": oc("get", "clusterversion", "version", "-o", "jsonpath={.status.desired.version}"),
    "platform": oc("get", "infrastructure", "cluster", "-o", "jsonpath={.status.platformStatus.type}") or "OpenShift",
    "openshiftAi": csv("redhat-ods-operator", "rhods-operator"),
    "agentSandbox": csv("openshift-operators", "agent-sandbox-operator"),
    "mcpGateway": csv("openshift-operators", "mcp-gateway"),
    "openshell": openshell,
    "openclaw": openclaw,
    "model": env.get("model", ""),      # the model's name is not a secret; the key never leaves .env
    "modelHost": "Red Hat MaaS",
}
print(json.dumps({k: v for k, v in facts.items() if v}))
PY

before=$(oc get configmap platform-facts -n ollivanders -o jsonpath='{.data.facts\.json}' 2>/dev/null || true)
oc create configmap platform-facts -n ollivanders --from-file=facts.json="$FACTS" \
  --dry-run=client -o yaml | oc apply -f - >/dev/null
echo "platform facts updated from the cluster"
# The pod reads them at start. Restart it only if they changed and it is already there.
if [[ "$before" != "$(cat "$FACTS")" ]] && oc get deploy/shop-front -n ollivanders >/dev/null 2>&1; then
  oc rollout restart deploy/shop-front -n ollivanders >/dev/null
  oc rollout status deploy/shop-front -n ollivanders --timeout=300s
fi
