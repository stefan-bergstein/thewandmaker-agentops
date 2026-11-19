#!/usr/bin/env python3
"""Install demo operators and AI components while preserving existing cluster configuration."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent


def oc_json(*args):
    result = subprocess.run(["oc", *args, "-o", "json", "--request-timeout=30s"],
                            capture_output=True, text=True, check=True)
    # oc create emits one JSON document per YAML object, not necessarily a List.
    objects, remaining = [], result.stdout.lstrip()
    decoder = json.JSONDecoder()
    while remaining:
        item, end = decoder.raw_decode(remaining)
        objects.append(item)
        remaining = remaining[end:].lstrip()
    return objects[0] if len(objects) == 1 else {"items": objects}


def manifest(path):
    data = oc_json("create", "--dry-run=client", "--validate=false", "-f", str(ROOT / path))
    return data.get("items", [data])


def apply(resource):
    subprocess.run(["oc", "apply", "-f", "-", "--request-timeout=30s"],
                   input=json.dumps(resource), text=True, check=True)


def install_operators():
    for resource in manifest("gitops/10-operators/subscriptions.yaml"):
        kind, metadata = resource["kind"], resource["metadata"]
        namespace = metadata.get("namespace")
        if kind in ("OperatorGroup", "Subscription"):
            existing = oc_json("get", kind, "-n", namespace)["items"]
            if kind == "Subscription":
                existing = [item for item in existing
                            if item["spec"]["name"] == resource["spec"]["name"]]
            if len(existing) > 1:
                sys.exit(f"Multiple {kind} resources in {namespace}; resolve the existing conflict first.")
            if existing:
                print(f"Reusing {kind} {namespace}/{existing[0]['metadata']['name']}", flush=True)
                continue
        apply(resource)


def managed_component_patch(desired):
    """Enable required components without disabling existing components or changing their options."""
    return {name: {"managementState": "Managed"}
            for name, component in desired["spec"]["components"].items()
            if component.get("managementState") == "Managed"}


def install_ai():
    desired = manifest("gitops/11-openshift-ai/datasciencecluster.yaml")[0]
    existing = oc_json("get", "datascienceclusters")["items"]
    if len(existing) > 1:
        sys.exit("Multiple DataScienceClusters found; select a supported single-cluster configuration first.")
    if existing:
        name = existing[0]["metadata"]["name"]
        patch = {"spec": {"components": managed_component_patch(desired)}}
        subprocess.run(["oc", "patch", "datasciencecluster", name, "--type=merge",
                        "-p", json.dumps(patch), "--request-timeout=30s"], check=True)
        print(f"Enabled demo components in existing DataScienceCluster {name}; preserved other settings", flush=True)
    else:
        name = desired["metadata"]["name"]
        apply(desired)
    subprocess.run(["bash", str(ROOT / "scripts/wait-for.sh"), "condition", "-",
                    f"datasciencecluster/{name}", "Ready", "1800"], check=True)


def main():
    if sys.argv[1:] == ["operators"]:
        install_operators()
    elif sys.argv[1:] == ["openshift-ai"]:
        install_ai()
    else:
        sys.exit("Usage: install-platform-resources.py operators|openshift-ai")


if __name__ == "__main__":
    main()
