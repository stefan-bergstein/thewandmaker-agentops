#!/usr/bin/env python3
"""Log in interactively with oc, honoring KUBECONFIG and the cluster identity provider.

Arguments are passed to oc login. Use the browser/interactive login for your cluster;
never put a token or password in a command line or this repository.
"""
import subprocess
import sys

if __name__ == "__main__":
    sys.exit(subprocess.call(["oc", "login", *sys.argv[1:]]))
