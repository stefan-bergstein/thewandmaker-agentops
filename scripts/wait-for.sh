#!/usr/bin/env bash
# Wait points for "make up-platform" on a fresh cluster. Each call waits until one thing is true,
# prints one line when it is, and fails after a timeout (seconds, default 900). Read-only.
# Works with bash 3.2 (macOS) and needs no "timeout" command.
#
#   wait-for.sh csv <namespace> <subscription> [timeout]     operator from that subscription: CSV Succeeded
#   wait-for.sh crd <crd-name> [<crd-name> ...]              CRDs exist and are Established
#   wait-for.sh exists <namespace|-> <kind/name> [timeout]   the object exists ("-" = cluster-scoped)
#   wait-for.sh condition <namespace|-> <kind/name> <condition> [timeout]   exists, then condition=True
#   wait-for.sh rollout <namespace> <deploy/name|sts/name> [timeout]       exists, then rolled out
#   wait-for.sh sa <namespace> <serviceaccount> [timeout]    service account with its pull secret (for builds)
set -euo pipefail

TIMEOUT_DEFAULT=900
log() { printf '[wait %s] %s\n' "$(date +%H:%M:%S)" "$*"; }

# until <timeout> <description> <command...>: run the command every 10 s until it succeeds.
until_ok() {
  local limit=$1 what=$2; shift 2
  local start=$SECONDS next=60
  until "$@" >/dev/null 2>&1; do
    if (( SECONDS - start >= limit )); then
      log "gave up after ${limit} s: $what"; return 1
    fi
    if (( SECONDS - start >= next )); then
      log "still waiting ($(( SECONDS - start )) s): $what"; next=$(( next + 60 ))
    fi
    sleep 10
  done
  log "ok after $(( SECONDS - start )) s: $what"
}

nsflag() { [[ "$1" == "-" ]] && echo "" || echo "-n $1"; }

csv_succeeded() {
  local ns=$1 sub=$2 csv
  # Existing clusters can use a different Subscription name for the same package.
  csv=$(oc get subscriptions.operators.coreos.com -n "$ns" -o json --request-timeout=25s |
    python3 -c 'import json,sys
items = [s for s in json.load(sys.stdin)["items"]
         if s["metadata"]["name"] == sys.argv[1] or s.get("spec", {}).get("name") == sys.argv[1]]
print(items[0].get("status", {}).get("installedCSV", "") if len(items) == 1 else "")' "$sub")
  [[ -n "$csv" ]] || return 1
  [[ "$(oc get csv "$csv" -n "$ns" -o jsonpath='{.status.phase}' 2>/dev/null)" == Succeeded ]]
}

crd_established() {
  [[ "$(oc get crd "$1" -o jsonpath='{.status.conditions[?(@.type=="Established")].status}' 2>/dev/null)" == True ]]
}

has_condition() {
  local ns=$1 obj=$2 cond=$3
  # shellcheck disable=SC2046
  [[ "$(oc get "$obj" $(nsflag "$ns") -o jsonpath="{.status.conditions[?(@.type==\"$cond\")].status}" 2>/dev/null)" == True ]]
}

rolled_out() {
  local ns=$1 obj=$2
  oc get "$obj" -n "$ns" >/dev/null 2>&1 || return 1
  oc rollout status "$obj" -n "$ns" --timeout=5s
}

sa_ready() {
  local ns=$1 sa=$2
  oc get sa "$sa" -n "$ns" >/dev/null 2>&1 || return 1
  # The image pull secret is added to the account by a controller a few seconds later.
  [[ -n "$(oc get sa "$sa" -n "$ns" -o jsonpath='{.imagePullSecrets[*].name}' 2>/dev/null)" ]]
}

cmd=${1:-}; shift || true
case "$cmd" in
  csv)
    until_ok "${3:-$TIMEOUT_DEFAULT}" "operator $2 in $1: CSV Succeeded" csv_succeeded "$1" "$2" ;;
  crd)
    for c in "$@"; do until_ok "$TIMEOUT_DEFAULT" "CRD $c established" crd_established "$c"; done ;;
  exists)
    # shellcheck disable=SC2046
    until_ok "${3:-$TIMEOUT_DEFAULT}" "$2 exists" oc get "$2" $(nsflag "$1") ;;
  condition)
    until_ok "${4:-$TIMEOUT_DEFAULT}" "$2: $3=True" has_condition "$1" "$2" "$3" ;;
  rollout)
    until_ok "${3:-$TIMEOUT_DEFAULT}" "$2 in $1 rolled out" rolled_out "$1" "$2" ;;
  sa)
    until_ok "${3:-$TIMEOUT_DEFAULT}" "service account $2 in $1 ready" sa_ready "$1" "$2" ;;
  *)
    sed -n '2,12p' "$0"; exit 2 ;;
esac
