"""Application entrypoint re-exports the FastAPI app defined in app.main."""

from app.main import app

__all__ = ["app"]
