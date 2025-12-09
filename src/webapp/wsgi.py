"""
WSGI entrypoint for production servers.
"""

from webapp.app import create_app

app = create_app()

