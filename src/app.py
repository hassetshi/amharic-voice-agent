"""
src/app.py — FastAPI application factory
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routes import call_routes, health_routes


def create_app() -> FastAPI:
    app = FastAPI(
        title="Amazon Consulting — Amharic Voice Agent",
        description="Bilingual English + Amharic voice agent for Amazon Consulting LLC",
        version="1.0.0"
    )

    # CORS — allow all origins for local dev
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routes
    app.include_router(health_routes.router)
    app.include_router(call_routes.router)

    return app


app = create_app()
