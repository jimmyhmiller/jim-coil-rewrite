#!/usr/bin/env python3
"""Build the pinned Ghostty embedding library without building the Ghostty app.

Coil builds also do this on demand through the `ghostty` native dependency.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / 'ghostty'))
import pinned

pinned.ensure()
print('Ghostty embedding library is ready:', pinned.DEST)
