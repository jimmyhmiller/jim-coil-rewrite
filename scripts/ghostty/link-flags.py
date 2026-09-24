#!/usr/bin/env python3
"""Coil native-dependency provider for the pinned Ghostty libraries.

Usage: link-flags.py internal|vt. Builds the libraries when stale, then prints
the selected static library as the linker argument.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pinned

if len(sys.argv) != 2 or sys.argv[1] not in pinned.LIBRARIES:
    raise SystemExit('usage: link-flags.py ' + '|'.join(pinned.LIBRARIES))
pinned.ensure()
print(pinned.LIBRARIES[sys.argv[1]])
