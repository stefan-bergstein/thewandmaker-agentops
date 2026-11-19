#!/usr/bin/env python3
"""Run a repository script locally, or on an explicitly configured bastion.

    python3 scripts/run-openshell.py gitops/02-openshell/provider-maas.sh

Local execution uses the source files in place and passes model settings in the child
environment. With a bastion, scripts are copied to ~/.olli/ and settings travel over SSH
stdin. Model keys never appear in command arguments.
"""
import os
import shlex
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_env():
    env = {}
    with open(os.path.join(ROOT, ".env")) as f:
        for line in f:
            line = line.rstrip("\n")
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    script, extra = sys.argv[1], sys.argv[2:]   # extra files are copied next to the script
    env = load_env()
    host, user = env.get("BASTION_HOST"), env.get("BASTION_USER")
    if bool(host) != bool(user):
        sys.exit("Set both BASTION_HOST and BASTION_USER, or leave both empty for local execution.")
    if not host:
        local_env = dict(os.environ)
        local_env["PATH"] = os.path.expanduser("~/.local/bin") + os.pathsep + local_env.get("PATH", "")
        local_env["NO_COLOR"] = "1"
        for source, destination in (("modelkey", "OPENAI_API_KEY"), ("model", "MAAS_MODEL")):
            if env.get(source):
                local_env[destination] = env[source]
        if env.get("modelendpoint"):
            local_env["MAAS_BASE_URL"] = env["modelendpoint"].split("/chat/completions")[0]
        local_env.setdefault("MODEL_GATEWAY_URL", "http://model-gateway.ollivanders.svc:8080/v1")
        result = subprocess.run(["bash", os.path.join(ROOT, script)], cwd=ROOT, env=local_env)
        sys.exit(result.returncode)
    target = f"{user}@{host}"
    if target.startswith("-"):
        sys.exit("Invalid bastion SSH target")
    subprocess.run(["ssh", "-o", "BatchMode=yes", target, "umask 077; mkdir -p ~/.olli"], check=True)
    subprocess.run(["scp", "-q", "-o", "BatchMode=yes"]
                   + [os.path.join(ROOT, p) for p in [script] + extra]
                   + [f"{target}:.olli/"], check=True)
    base = env["modelendpoint"].split("/chat/completions")[0]
    lines = [
        "export PATH=$HOME/.local/bin:$PATH NO_COLOR=1",
        "export ROSA_API_URL=" + shlex.quote(env.get("ROSA_API_URL", "")),
        "export OPENAI_API_KEY=" + shlex.quote(env["modelkey"]),
        "export MAAS_BASE_URL=" + shlex.quote(base),
        "export MAAS_MODEL=" + shlex.quote(env["model"]),
        "export MODEL_GATEWAY_URL=" + shlex.quote(os.environ.get("MODEL_GATEWAY_URL",
                                                  "http://model-gateway.ollivanders.svc:8080/v1")),
    ] + [f"export {k}=" + shlex.quote(os.environ[k]) for k in ("APPRENTICE_NAME",) if os.environ.get(k)] + [
        "bash ~/.olli/" + shlex.quote(os.path.basename(script)),
    ]
    r = subprocess.run(["ssh", "-o", "BatchMode=yes", target, "bash -s"],
                       input="\n".join(lines) + "\n", text=True)
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
