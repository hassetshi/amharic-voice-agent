"""
src/services.py — STT / LLM / TTS / GHL integrations
"""

import re
import struct
import base64
import unicodedata
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

    # ── STEP 2: RAG — inject relevant knowledge chunks ──────────────────
    if company and company.rag and not is_greeting and user_text.strip():
        print(f"[2/4 RAG] Searching knowledge base for: {user_text[:60]}")
        context = company.rag.search(user_text, top_k=3)
        if context:
            system += f"\n\n══ RETRIEVED CONTEXT (use this to answer precisely) ══\n{context}"
            print(f"[2/4 RAG] Injected {len(context)} chars into prompt")
        else:
            print("[2/4 RAG] No relevant chunks found")

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


def _google_tts(text: str, mulaw: bool = True, lang: str = "amharic") -> bytes:
    """Google Cloud TTS — supports Amharic (am-ET) and English (en-US)."""
    if lang == "english":
        lang_code  = "en-US"
        voice_name = config.GOOGLE_TTS_VOICE_EN
    else:
        lang_code  = "am-ET"
        voice_name = config.GOOGLE_TTS_VOICE_AM
    try:
        payload = {
            "input": {"text": text},
            "voice": {
                "languageCode": lang_code,
                "name": voice_name,
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
    """Route each line to Google TTS with the correct language voice.

    Primarily-Amharic lines (>=50% Ethiopic chars) → Google TTS am-ET voice
    English / mixed lines → Google TTS en-US voice
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return b""

    parts: list[bytes] = []
    for line in lines:
        lang = "amharic" if _is_primarily_amharic(line) else "english"
        parts.append(_google_tts(line, mulaw=mulaw, lang=lang))

    return b"".join(parts)


def clean_for_tts(text: str) -> str:
    """Remove emojis, markdown, and symbols that sound bad when spoken aloud."""
    # Strip markdown bold/italic/headers
    text = re.sub(r"\*{1,3}(.*?)\*{1,3}", r"\1", text)
    text = re.sub(r"#{1,6}\s*", "", text)
    text = re.sub(r"`{1,3}.*?`{1,3}", "", text, flags=re.DOTALL)
    # Strip emojis and other symbols
    cleaned = []
    for char in text:
        cat = unicodedata.category(char)
        # Keep: letters (L), numbers (N), punctuation (P), spaces (Z), Ethiopic
        if cat.startswith(("L", "N", "P", "Z")) or char in "\n ":
            cleaned.append(char)
    text = "".join(cleaned)
    # Collapse extra whitespace/newlines
    text = re.sub(r"\n{2,}", "\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def text_to_speech(text: str, language: str = "auto") -> bytes:
    """Convert text to mulaw audio bytes compatible with Twilio.

    language="amharic"  → Google TTS am-ET voice
    language="english"  → Google TTS en-US voice
    language="bilingual"→ per-line auto-detect, Google TTS for both
    language="auto"     → auto-detect from text content
    """
    text = clean_for_tts(text)
    if not text:
        return b""
    if language == "amharic":
        return _google_tts(text, mulaw=True, lang="amharic")
    if language == "english":
        return _google_tts(text, mulaw=True, lang="english")
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
    """Transcribe mulaw 8kHz audio using Google Cloud Speech-to-Text.

    For bilingual lines, language="am-ET,en-US" triggers automatic
    language detection — Google picks whichever language best matches.
    """
    if not audio_bytes or not config.GOOGLE_TTS_API_KEY:
        return ""
    try:
        # Bilingual: split into primary + alternative languages
        langs = [l.strip() for l in language.split(",")]
        stt_config = {
            "encoding": "MULAW",
            "sampleRateHertz": 8000,
            "languageCode": langs[0],
            "enableAutomaticPunctuation": True,
        }
        if len(langs) > 1:
            stt_config["alternativeLanguageCodes"] = langs[1:]

        payload = {
            "config": stt_config,
            "audio": {"content": base64.b64encode(audio_bytes).decode("utf-8")},
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
                transcript = results[0]["alternatives"][0]["transcript"].strip()
                detected   = results[0].get("languageCode", langs[0])
                print(f"[1/4 STT] Detected language: {detected}")
                return transcript
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

    # Phone: keep E.164 format (+1XXXXXXXXXX) — GHL accepts it and deduplicates on it
    caller_raw = session.caller or ""
    # Normalize: ensure +1 prefix for 10-digit US numbers without country code
    if caller_raw and not caller_raw.startswith("+"):
        caller_raw = f"+1{caller_raw}"
    phone = caller_raw   # send full E.164 to GHL

    # Name: use what was extracted from speech, fall back to the caller's number
    extracted_name = session.contact.get("name", "").strip()
    first_name = extracted_name if extracted_name else f"Caller {phone[-4:]}" if phone else "Voice Caller"

    # Company tag from session
    company_tag = company.id.replace("_", "-") if company else "amazon-consulting"

    payload = {
        "firstName":       first_name,
        "phone":           phone,
        "caller":          caller_raw,
        "source":          "Amharic Voice Agent",
        "language":        session.language,
        "service":         session.contact.get("service", "General Inquiry"),
        "callSid":         session.call_sid,
        "transcript":      session.full_transcript_text(),
        "summary":         session.summary(),
        "appointmentRequested": session.contact.get("appointmentRequested", "false"),
        "appointmentDay":  session.contact.get("preferredDay", ""),
        "tags":            f"voice-agent,{session.language},{company_tag}",
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
