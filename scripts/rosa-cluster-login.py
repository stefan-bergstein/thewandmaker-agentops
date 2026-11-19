#!/usr/bin/env python3
"""Log in to the cluster again (tokens last 24 hours) and refresh local/kubeconfig.

Uses the cluster-admin password from local/cluster-admin-password (created with "rosa create admin")
and the API URL from .env (ROSA_API_URL). Nothing secret is printed.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def env_value(key):
    with open(os.path.join(ROOT, ".env")) as f:
        for line in f:
            if line.startswith(key + "="):
                return line.rstrip("\n").split("=", 1)[1].strip()
    sys.exit(f"{key} missing in .env")


def main():
    with open(os.path.join(ROOT, "local", "cluster-admin-password")) as f:
        password = f.read().strip()
    env = dict(os.environ, KUBECONFIG=os.path.join(ROOT, "local", "kubeconfig"))
    r = subprocess.run(["oc", "login", env_value("ROSA_API_URL"), "-u", "cluster-admin", "-p", password,
                        "--insecure-skip-tls-verify=false"], env=env, capture_output=True, text=True)
    out = (r.stdout + r.stderr).replace(password, "***")
    print("\n".join(l for l in out.splitlines() if "password" not in l.lower())[:600])
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
