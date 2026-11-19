#!/usr/bin/env bash
# Install OpenShell 0.0.116 (Red Hat images) on the current cluster. Connect the CLI with make cli-connect.
# Idempotent: run it again after a change. Needs KUBECONFIG pointing at the cluster.
set -euo pipefail
cd "$(dirname "$0")"

VERSION=0.0.116
NS=openshell
SCC=${OPENSHELL_SCC:-openshell-sandbox-minimum-required}

oc apply -f 00-namespace-scc.yaml
if [[ "$SCC" == privileged ]]; then
  echo "Fallback: granting the privileged SCC to openshell-sandbox"
  oc adm policy add-scc-to-user privileged -z openshell-sandbox -n "$NS"
fi

DOMAIN=$(oc get ingresses.config.openshift.io cluster -o jsonpath='{.spec.domain}')
ROUTE_HOST="openshell-${NS}.${DOMAIN}"

helm upgrade --install openshell oci://ghcr.io/nvidia/openshell/helm-chart \
  --version "$VERSION" --namespace "$NS" \
  -f values.yaml \
  --set "pkiInitJob.serverDnsNames[0]=${ROUTE_HOST}" \
  --wait --timeout 10m

oc create route passthrough openshell --service=openshell --port=8080 \
  --hostname="$ROUTE_HOST" -n "$NS" --dry-run=client -o yaml | oc apply -f -

echo "Gateway: https://${ROUTE_HOST}"
