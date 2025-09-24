"""Test configuration for ensuring direct module imports succeed."""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure the project root (containing modules like `calc`, `models`, `services`) is available on
# the Python import path when running tests with the default ``pytest`` command.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT_STR = str(PROJECT_ROOT)
if PROJECT_ROOT_STR not in sys.path:
    sys.path.insert(0, PROJECT_ROOT_STR)
