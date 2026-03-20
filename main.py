#!/usr/bin/env python3
"""
Amazon Consulting LLC — Amharic Voice Agent
main.py — Entry point
"""

import uvicorn
from src.app import create_app

app = create_app()

if __name__ == "__main__":
    print("\n" + "═" * 55)
    print("  🇪🇹  Amazon Consulting — Amharic Voice Agent")
    print("  📞  POST /incoming-call  ← Twilio webhook")
    print("  🔌  WS   /media-stream   ← Audio stream")
    print("  ❤️   GET  /health         ← Health check")
    print("  🧪  GET  /test-amharic   ← TTS test")
    print("═" * 55 + "\n")

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,           # auto-restart on code changes
        log_level="info"
    )
