#!/usr/bin/env python3
"""Open OpenShell's terminal UI locally, or on the optional bastion.

Run make shell-ui in an interactive terminal. Pick apprentice, Enter, then l for its audit log.
"""
import os
import shlex
import subprocess
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def main():
    spec = spec_from_file_location("runner", Path(__file__).with_name("run-openshell.py"))
    runner = module_from_spec(spec)
    spec.loader.exec_module(runner)
    env = runner.load_env()
    host, user = env.get("BASTION_HOST"), env.get("BASTION_USER")
    if bool(host) != bool(user):
        sys.exit("Set both BASTION_HOST and BASTION_USER, or neither.")
    if host:
        target = f"{user}@{host}"
        if target.startswith("-"):
            sys.exit("Invalid bastion SSH target")
        command = ["ssh", "-t", target, "bash -lc " + shlex.quote("export PATH=$HOME/.local/bin:$PATH; openshell term")]
    else:
        os.environ["PATH"] = os.path.expanduser("~/.local/bin") + os.pathsep + os.environ.get("PATH", "")
        command = ["openshell", "term"]
    sys.exit(subprocess.call(command))


if __name__ == "__main__":
    main()
