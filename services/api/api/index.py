"""Vercel ASGI entry point for the hosted Artae control plane."""

from video_intelligence_api.main import create_app

app = create_app()
