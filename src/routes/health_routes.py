"""
src/routes/health_routes.py — Health check + local test endpoints
"""

import os
from fastapi import APIRouter
from fastapi.responses import Response, JSONResponse
from ..config import config
from ..session import session_manager
from ..services import text_to_speech_mp3, generate_response
from ..session import CallSession

router = APIRouter()


@router.get("/")
async def root():
    return {
        "agent":    "Amazon Consulting — Amharic Voice Agent",
        "status":   "online",
        "version":  "1.0.0",
        "languages": ["English 🇺🇸", "Amharic 🇪🇹"],
    }


@router.get("/health")
async def health():
    missing = config.validate()
    return {
        "status":          "ok" if not missing else "degraded",
        "missing_keys":    missing,
        "active_sessions": session_manager.count(),
        "business":        config.BUSINESS_NAME,
        "phone":           config.BUSINESS_PHONE,
        "base_url":        config.BASE_URL,
    }


# ── LOCAL TEST: hear Amharic TTS in your browser ──────────────────────────
@router.get("/test-amharic")
async def test_amharic():
    """
    Hit this in your browser to hear the Amharic greeting.
    Returns MP3 audio you can play directly.
    GET http://localhost:8000/test-amharic
    """
    text = (
        "ሰላም! ወደ አማዞን ኮንሰልቲንግ እንኳን ደህና መጡ። "
        "Hello! Welcome to Amazon Consulting. "
        "አማርኛ ወይም እንግሊዝኛ ማውራት ይችላሉ። "
        "How can I help you today?"
    )
    audio = text_to_speech_mp3(text)
    if audio:
        return Response(content=audio, media_type="audio/mpeg")
    return JSONResponse({"error": "TTS failed — check ELEVENLABS_API_KEY"}, status_code=500)


@router.get("/test-financial")
async def test_financial():
    """Test Financial Services Amharic response."""
    text = (
        "የፋይናንስ አገልግሎቶቻችን፡ አካውንቲንግ፣ ቡክኪፒንግ፣ "
        "እና ፌዴራልና ስቴት ታክስ ዲክላሬሽን ናቸው። "
        "ቀጠሮ ልያዝልዎ? ስምዎን ይንገሩኝ።"
    )
    audio = text_to_speech_mp3(text)
    if audio:
        return Response(content=audio, media_type="audio/mpeg")
    return JSONResponse({"error": "TTS failed"}, status_code=500)


@router.get("/test-immigration")
async def test_immigration():
    """Test Immigration Amharic response."""
    text = (
        "ቪዛ አፕሊኬሽን፣ ግሪን ካርድ፣ ሲቲዘንሺፕ፣ "
        "እና የኤምባሲ ቀጠሮ እርዳታ እንሰጣለን። "
        "የኢሚግሬሽን ጉዳይዎ ምንድን ነው?"
    )
    audio = text_to_speech_mp3(text)
    if audio:
        return Response(content=audio, media_type="audio/mpeg")
    return JSONResponse({"error": "TTS failed"}, status_code=500)


@router.get("/test-chat")
async def test_chat(message: str = "ሰላም"):
    """
    Test the full AI pipeline (no phone needed).
    GET http://localhost:8000/test-chat?message=ሰላም
    GET http://localhost:8000/test-chat?message=I need help with immigration
    """
    session = CallSession(call_sid="LOCAL-TEST", caller="+10000000000")
    reply = await generate_response(session, message, is_greeting=False)
    lang  = "amharic" if any(ord(c) in range(0x1200, 0x137F) for c in message) else "english"
    return {
        "input":     message,
        "language":  lang,
        "response":  reply,
        "tip":       "Add ?message=YOUR_TEXT to test different inputs"
    }


@router.get("/sessions")
async def list_sessions():
    return {
        "count":    session_manager.count(),
        "sessions": session_manager.list_ids()
    }
