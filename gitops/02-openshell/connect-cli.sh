#!/usr/bin/env bash
# Point the openshell CLI at the gateway on the cluster.
# Needs an authenticated oc context with access to the gateway client certificate.
set -euo pipefail
NS=openshell
GW=${OPENSHELL_GATEWAY_NAME:-olli}
oc whoami >/dev/null || { echo "Log in with oc login before connecting OpenShell." >&2; exit 1; }
HOST=$(oc get route openshell -n "$NS" -o jsonpath='{.spec.host}')
DIR=${XDG_CONFIG_HOME:-$HOME/.config}/openshell/gateways/$GW
# The mTLS bundle has to be in place before "gateway add".
( umask 077; mkdir -p "$DIR/mtls"
  for k in ca.crt tls.crt tls.key; do
    oc -n "$NS" get secret openshell-client-tls -o jsonpath="{.data.${k//./\\.}}" | openssl base64 -d -A > "$DIR/mtls/$k"
  done )
# OpenShell 0.0.116 imports the machine's package-managed gateway certificates on
# --local registration, overwriting this cluster's bundle. Disable that import;
# TLS verification still uses the cluster CA and client certificate copied above.
# https://github.com/NVIDIA/OpenShell/blob/v0.0.116/crates/openshell-cli/src/commands/gateway.rs
export OPENSHELL_LOCAL_TLS_DIR=/dev/null
if output=$(openshell gateway add "https://$HOST" --local --name "$GW" 2>&1); then
  printf '%s\n' "$output"
else
  case "$output" in
    *"Gateway '$GW' already exists."*)
      # Refresh only CLI metadata so a previous cluster's endpoint cannot survive.
      # gateway remove preserves the mTLS files and does not stop the server.
      openshell gateway remove "$GW"
      openshell gateway add "https://$HOST" --local --name "$GW"
      ;;
    *) printf '%s\n' "$output" >&2; exit 1 ;;
  esac
fi
openshell gateway select "$GW" >/dev/null
openshell status --gateway "$GW"
