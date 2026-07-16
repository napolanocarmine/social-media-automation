"""ASGI entrypoint per Vercel Python runtime."""

from social_automation.api.main import app

__all__ = ["app"]
