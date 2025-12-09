"""
Test configuration.

We try to load pytest-asyncio so pytest recognizes asyncio_mode. If the plugin
isn't available in the active interpreter, we warn but do not hard-fail.
"""

from __future__ import annotations

import importlib
import warnings

try:
    importlib.import_module("pytest_asyncio")
except ImportError:
    warnings.warn(
        "pytest-asyncio is not installed in this interpreter; async tests may be limited.",
        RuntimeWarning,
        stacklevel=1,
    )
    pytest_plugins: list[str] = []
else:
    pytest_plugins = ["pytest_asyncio"]

