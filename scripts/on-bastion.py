#!/usr/bin/env python3
"""Compatibility entry point; scripts now run locally unless a bastion is configured."""
import runpy
from pathlib import Path

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).with_name("run-openshell.py")), run_name="__main__")
