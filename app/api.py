"""Minimal HTTP API: health check endpoint for load balancers and orchestrators."""

from fastapi import FastAPI

from app.core.config import settings

app = FastAPI(title=settings.app_name)


@app.get("/health")
async def health() -> dict[str, str]:
    """Process liveness — returns 200 when the service process is running."""
    return {"status": "ok", "service": settings.app_name}
