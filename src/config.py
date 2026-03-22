"""
src/config.py — All configuration loaded from .env
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # ── Deepgram (STT) ─────────────────────────────────
    DEEPGRAM_API_KEY: str   = os.getenv("DEEPGRAM_API_KEY", "")
    DEEPGRAM_MODEL: str     = "nova-2"
    DEEPGRAM_LANGUAGE: str  = "en-US"   # Deepgram live STT; Amharic detected via Unicode post-transcription

    # ── Anthropic Claude (LLM) ─────────────────────────
    ANTHROPIC_API_KEY: str    = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL: str      = "claude-haiku-4-5-20251001"  # fast, low-latency for voice
    ANTHROPIC_MAX_TOKENS: int = 200      # keep responses short for voice
    ANTHROPIC_TEMPERATURE: float = 0.4

    # ── ElevenLabs (TTS — English) ─────────────────────
    ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "")
    ELEVENLABS_VOICE_ID: str= os.getenv("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")
    ELEVENLABS_MODEL: str   = "eleven_turbo_v2_5"   # multilingual, low latency

    # ── Google Cloud TTS ────────────────────────────────
    GOOGLE_TTS_API_KEY: str       = os.getenv("GOOGLE_TTS_API_KEY", "")
    GOOGLE_TTS_VOICE_AM: str      = "am-ET-Standard-A"   # Amharic female voice
    GOOGLE_TTS_VOICE_EN: str      = "en-US-Standard-C"   # English female voice
    GOOGLE_TTS_LANGUAGE: str      = "am-ET"              # kept for backwards compat

    # ── Twilio (Phone) ─────────────────────────────────
    TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN: str  = os.getenv("TWILIO_AUTH_TOKEN", "")
    TWILIO_PHONE: str       = os.getenv("TWILIO_PHONE_NUMBER", "")

    # ── GHL CRM ────────────────────────────────────────
    GHL_WEBHOOK_URL: str    = os.getenv("GHL_WEBHOOK_URL", "")
    GHL_API_KEY: str        = os.getenv("GHL_API_KEY", "")         # Private Integration token
    GHL_LOCATION_ID: str    = os.getenv("GHL_LOCATION_ID", "")     # Location ID from GHL URL

    # ── Server ─────────────────────────────────────────
    BASE_URL: str           = os.getenv("BASE_URL", "http://localhost:8000")
    PORT: int               = int(os.getenv("PORT", "8000"))

    # ── Business Info ──────────────────────────────────
    BUSINESS_NAME: str      = "Amazon Consulting LLC"
    BUSINESS_PHONE: str     = "(240) 641-1515"
    BUSINESS_ADDRESS: str   = "914 Silver Spring Ave, Silver Spring, MD 20910"
    BUSINESS_WEBSITE: str   = "dmvamazon.com"

    @classmethod
    def validate(cls) -> list[str]:
        """Returns list of missing required keys."""
        missing = []
        required = {
            "DEEPGRAM_API_KEY":   cls.DEEPGRAM_API_KEY,
            "ANTHROPIC_API_KEY":  cls.ANTHROPIC_API_KEY,
            "ELEVENLABS_API_KEY": cls.ELEVENLABS_API_KEY,
        }
        for key, val in required.items():
            if not val:
                missing.append(key)
        return missing


config = Config()
