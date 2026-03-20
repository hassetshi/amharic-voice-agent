"""
src/services.py — STT / LLM / TTS / GHL integrations
"""

import re
import struct
import base64
import httpx
import anthropic
from elevenlabs.client import ElevenLabs
from elevenlabs import Voice, VoiceSettings
from .config import config
from .prompts import SYSTEM_PROMPT, AMHARIC_SYSTEM_PROMPT, ENGLISH_SYSTEM_PROMPT
from .session import CallSession

# ── Clients ────────────────────────────────────────────────────────────────
anthropic_client  = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)
elevenlabs_client = ElevenLabs(api_key=config.ELEVENLABS_API_KEY)


# ════════════════════════════════════════════════════════════════════════════
# LANGUAGE DETECTION
# ════════════════════════════════════════════════════════════════════════════
AMHARIC_RANGE = range(0x1200, 0x137F)   # Ethiopic Unicode block

def detect_language(text: str) -> str:
    """Returns 'amharic' if Ethiopic chars found, else 'english'."""
    for char in text:
        if ord(char) in AMHARIC_RANGE:
            return "amharic"
    return "english"


# ════════════════════════════════════════════════════════════════════════════
# LLM — Claude generates bilingual responses
# ════════════════════════════════════════════════════════════════════════════
async def generate_response(session: CallSession, user_text: str,
                             is_greeting: bool = False) -> str:
    """Call Claude with full conversation history and return agent reply."""
    from .prompts import get_system_prompt
    from .company import get_by_id, default_company

    company = get_by_id(session.company_id) if session.company_id else default_company()

    # Build message list — must start with 'user' for Anthropic
    messages = list(session.messages)
    if messages and messages[0]["role"] == "assistant":
        messages = [{"role": "user", "content": "START_CALL_GREETING"}] + messages

    if is_greeting:
        messages.append({"role": "user", "content": "START_CALL_GREETING"})
    else:
        messages.append({"role": "user", "content": user_text})

    system = get_system_prompt(company, session.language) if company else AMHARIC_SYSTEM_PROMPT

    try:
        response = await anthropic_client.messages.create(
            model=config.ANTHROPIC_MODEL,
            system=system,
            messages=messages,
            max_tokens=config.ANTHROPIC_MAX_TOKENS,
            temperature=config.ANTHROPIC_TEMPERATURE,
        )
        return response.content[0].text.strip()

    except Exception as e:
        print(f"[LLM ERROR] {e}")
        fallback = company.greeting_amharic if company else "ሰላም! እንዴት ልረዳዎ?"
        return fallback


# ════════════════════════════════════════════════════════════════════════════
# TTS — Routes Amharic → Google Cloud TTS, English → ElevenLabs
# ════════════════════════════════════════════════════════════════════════════

def _strip_wav_header(data: bytes) -> bytes:
    """Find the 'data' chunk in a WAV file and return only raw PCM bytes."""
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        return data  # not a WAV — return as-is
    pos = 12
    while pos + 8 <= len(data):
        chunk_id   = data[pos:pos + 4]
        chunk_size = struct.unpack_from("<I", data, pos + 4)[0]
        if chunk_id == b"data":
            return data[pos + 8:]
        pos += 8 + chunk_size
    return data  # fallback


def _google_tts(text: str, mulaw: bool = True) -> bytes:
    """Google Cloud TTS — native Amharic voice (am-ET-Standard-A)."""
    try:
        payload = {
            "input": {"text": text},
            "voice": {
                "languageCode": config.GOOGLE_TTS_LANGUAGE,
                "name": config.GOOGLE_TTS_VOICE,
            },
            "audioConfig": {
                "audioEncoding": "MULAW" if mulaw else "MP3",
                "sampleRateHertz": 8000,
            },
        }
        with httpx.Client() as client:
            r = client.post(
                "https://texttospeech.googleapis.com/v1/text:synthesize",
                json=payload,
                params={"key": config.GOOGLE_TTS_API_KEY},
                timeout=10.0,
            )
            r.raise_for_status()
            audio = base64.b64decode(r.json()["audioContent"])
            # Google returns MULAW with a WAV header — Twilio needs raw bytes
            if mulaw:
                audio = _strip_wav_header(audio)
            return audio
    except Exception as e:
        print(f"[GOOGLE TTS ERROR] {e}")
        return b""


def _elevenlabs_tts(text: str, mulaw: bool = True) -> bytes:
    """ElevenLabs TTS — used for English responses."""
    try:
        fmt = "ulaw_8000" if mulaw else "mp3_44100_128"
        settings = VoiceSettings(
            stability=0.5,
            similarity_boost=0.8,
            style=0.2,
            use_speaker_boost=True,
        )
        audio_generator = elevenlabs_client.generate(
            text=text,
            voice=Voice(voice_id=config.ELEVENLABS_VOICE_ID, settings=settings),
            model=config.ELEVENLABS_MODEL,
            output_format=fmt,
        )
        return b"".join(audio_generator)
    except Exception as e:
        tag = "TTS ERROR" if mulaw else "TTS MP3 ERROR"
        print(f"[{tag}] {e}")
        return b""


def _is_primarily_amharic(text: str) -> bool:
    """True if Ethiopic letters make up 50%+ of all alphabetical characters."""
    alpha = [c for c in text if c.isalpha()]
    if not alpha:
        return False
    ethiopic = sum(1 for c in alpha if 0x1200 <= ord(c) <= 0x137F)
    return ethiopic / len(alpha) >= 0.50


def _route_tts(text: str, mulaw: bool) -> bytes:
    """Route each line to the right TTS engine and concatenate.

    Primarily-Amharic lines (>=50% Ethiopic chars) → Google TTS (am-ET-Standard-A)
    English / mixed lines → ElevenLabs (eleven_turbo_v2_5, multilingual)
    """
    if not config.GOOGLE_TTS_API_KEY:
        return _elevenlabs_tts(text, mulaw=mulaw)

    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return b""

    parts: list[bytes] = []
    for line in lines:
        if _is_primarily_amharic(line):
            parts.append(_google_tts(line, mulaw=mulaw))
        else:
            parts.append(_elevenlabs_tts(line, mulaw=mulaw))

    return b"".join(parts)


def text_to_speech(text: str, language: str = "auto") -> bytes:
    """Convert text to mulaw audio bytes compatible with Twilio.

    language="amharic" → always Google TTS
    language="english" → always ElevenLabs
    language="auto"    → auto-detect from text content
    """
    if language == "amharic":
        return _google_tts(text, mulaw=True)
    if language == "english":
        return _elevenlabs_tts(text, mulaw=True)
    return _route_tts(text, mulaw=True)


def text_to_speech_mp3(text: str) -> bytes:
    """Convert text to MP3 — used for local testing."""
    return _route_tts(text, mulaw=False)


def audio_to_base64(audio_bytes: bytes) -> str:
    return base64.b64encode(audio_bytes).decode("utf-8")


# ════════════════════════════════════════════════════════════════════════════
# STT — Google Cloud Speech-to-Text (supports Amharic am-ET)
# ════════════════════════════════════════════════════════════════════════════
async def google_stt(audio_bytes: bytes, language: str = "am-ET") -> str:
    """Transcribe mulaw 8kHz audio using Google Cloud Speech-to-Text."""
    if not audio_bytes or not config.GOOGLE_TTS_API_KEY:
        return ""
    try:
        payload = {
            "config": {
                "encoding": "MULAW",
                "sampleRateHertz": 8000,
                "languageCode": language,
                "enableAutomaticPunctuation": True,
            },
            "audio": {
                "content": base64.b64encode(audio_bytes).decode("utf-8")
            },
        }
        async with httpx.AsyncClient() as client:
            r = await client.post(
                "https://speech.googleapis.com/v1/speech:recognize",
                json=payload,
                params={"key": config.GOOGLE_TTS_API_KEY},
                timeout=15.0,
            )
            print(f"[GOOGLE STT] HTTP {r.status_code} | {r.text[:200]}")
            r.raise_for_status()
            results = r.json().get("results", [])
            if results:
                return results[0]["alternatives"][0]["transcript"].strip()
            print("[GOOGLE STT] Empty results — no speech detected")
    except Exception as e:
        print(f"[GOOGLE STT ERROR] {e}")
    return ""


# ════════════════════════════════════════════════════════════════════════════
# CONTACT EXTRACTION — pulls name/phone/service from transcript text
# ════════════════════════════════════════════════════════════════════════════
SERVICE_KEYWORDS = {
    # English
    "tax":         "Financial Services",
    "accounting":  "Financial Services",
    "bookkeeping": "Financial Services",
    "ticket":      "Travel & Documents",
    "flight":      "Travel & Documents",
    "passport":    "Travel & Documents",
    "immigration": "Immigration & Embassy",
    "visa":        "Immigration & Embassy",
    "green card":  "Immigration & Embassy",
    "embassy":     "Immigration & Embassy",
    "citizenship": "Immigration & Embassy",
    "cargo":       "Cargo & Shipping",
    "shipping":    "Cargo & Shipping",
    "business":    "Business & Legal",
    "notary":      "Business & Legal",
    "llc":         "Business & Legal",
    # Amharic
    "ታክስ":         "Financial Services",
    "ግብር":         "Financial Services",
    "አካውንቲንግ":    "Financial Services",
    "ቡክኪፒንግ":     "Financial Services",
    "ፋይናንስ":       "Financial Services",
    "ትኬት":         "Travel & Documents",
    "አውሮፕላን":      "Travel & Documents",
    "ፓስፖርት":       "Travel & Documents",
    "ኢሚግሬሽን":      "Immigration & Embassy",
    "ቪዛ":          "Immigration & Embassy",
    "ግሪን ካርድ":    "Immigration & Embassy",
    "ኤምባሲ":        "Immigration & Embassy",
    "ሲቲዘንሺፕ":     "Immigration & Embassy",
    "ካርጎ":         "Cargo & Shipping",
    "ሺፒንግ":        "Cargo & Shipping",
    "ቢዝነስ":        "Business & Legal",
    "ኖታሪ":         "Business & Legal",
}


def extract_contact_info(session: CallSession, text: str):
    """Extract phone numbers and service intent from caller speech."""
    text_lower = text.lower()

    # Phone number
    phone_match = re.search(r'\b(\d{3}[-.\s]?\d{3}[-.\s]?\d{4})\b', text)
    if phone_match:
        session.set_contact("phone", phone_match.group(1))

    # Service keyword matching
    for keyword, service in SERVICE_KEYWORDS.items():
        if keyword in text_lower or keyword in text:
            session.set_contact("service", service)
            break

    # Appointment keywords
    appt_en = ["appointment", "book", "schedule", "meet"]
    appt_am = ["ቀጠሮ", "ልያዝ", "ስምምነት"]
    if any(k in text_lower for k in appt_en) or any(k in text for k in appt_am):
        session.set_contact("appointmentRequested", "true")


# ════════════════════════════════════════════════════════════════════════════
# GHL CRM — POST call data to GoHighLevel webhook
# ════════════════════════════════════════════════════════════════════════════
async def send_to_ghl(session: CallSession):
    """Send call summary and contact data to GHL inbound webhook."""
    from .company import get_by_id, default_company
    company = get_by_id(session.company_id) if session.company_id else default_company()
    webhook_url = (company.ghl_webhook_url if company else "") or config.GHL_WEBHOOK_URL
    if not webhook_url or "YOUR_HOOK_ID" in webhook_url:
        print("[GHL] ⚠️  Webhook URL not configured — skipping CRM update")
        return

    # Always use the Twilio caller ID as phone — guaranteed to be valid
    phone = session.caller.replace("+1", "").replace("+", "") if session.caller else ""

    payload = {
        "firstName":       session.contact.get("name", "Amharic Caller"),
        "phone":           phone,
        "caller":          session.caller,
        "source":          "Amharic Voice Agent",
        "language":        session.language,
        "service":         session.contact.get("service", "General Inquiry"),
        "callSid":         session.call_sid,
        "transcript":      session.full_transcript_text(),
        "summary":         session.summary(),
        "appointmentDay":  session.contact.get("preferredDay", ""),
        "tags":            "voice-agent,amharic,amazon-consulting",
    }

    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10.0
            )
        session.ghl_sent = True
        print(f"[GHL] ✅ Sent → HTTP {r.status_code} | {session.summary()}")
    except Exception as e:
        print(f"[GHL] ❌ Error: {e}")
