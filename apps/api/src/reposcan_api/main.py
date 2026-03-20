"""ASGI entrypoint for local development."""

from .app import create_app

app = create_app()
