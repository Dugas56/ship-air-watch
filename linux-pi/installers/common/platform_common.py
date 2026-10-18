#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path

def load_config(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))

def banner(name: str):
    print("=" * 64)
    print(name)
    print("=" * 64)

def emit(kind: str, text: str):
    print(f"{kind}: {text}")
