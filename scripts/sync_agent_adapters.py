#!/usr/bin/env python3
"""Compatibility entry point for the main repo-local adapter installer."""
import runpy
from pathlib import Path

if __name__ == "__main__":
    entrypoint = Path(__file__).resolve().parents[1] / ".agents/adapters/sync.py"
    runpy.run_path(str(entrypoint), run_name="__main__")
