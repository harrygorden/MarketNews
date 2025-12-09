"""
Root WSGI entrypoint for Azure App Service deployment.

This file adds the 'src' directory to the Python path so that
the webapp package can be imported correctly when using gunicorn.
"""

import os
import sys

# Add src directory to Python path for the src layout
src_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from webapp.wsgi import app  # noqa: E402

# Expose app for gunicorn
__all__ = ["app"]

