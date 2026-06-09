"""ASGI entry point for the Pulice API server."""

from pulice.api import create_api

app = create_api()
