"""
src/routes/call_routes.py — Twilio webhook + WebSocket media stream

STT: Google Cloud Speech-to-Text (am-ET) — Deepgram does not support Amharic.
VAD: Simple mulaw energy threshold to detect end of caller utterance.
"""

import json
import asyncio
import base64
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from twilio.twiml.voice_response import VoiceResponse, Connect, Stream, Gather  # noqa: F401

from ..config import config
from ..session import session_manager
from ..company import get_by_number, default_company
from ..services import (
    generate_response,
    text_to_speech,
    audio_to_base64,
    extract_contact_info,
    extract_name_from_reply,
    send_to_ghl,
    google_stt,
)

router = APIRouter()

# ── VAD tunables ─────────────────────────────────────────────────────────────
# Twilio sends 20 ms mulaw chunks (160 bytes at 8 kHz).
SILENCE_THRESHOLD  = 8    # mulaw energy 0-127; below this = silent
SILENCE_CHUNKS     = 45   # 45 × 20 ms = 900 ms of silence → end of utterance
MIN_SPEECH_CHUNKS  = 8    # 8 × 20 ms = 160 ms minimum speech to process
MAX_BUFFER_CHUNKS  = 400  # 400 × 20 ms = 8 s max recording per utterance

# ── Language → Google STT BCP-47 code ────────────────────────────────────────
# Bilingual sends "am-ET,en-US" — Google auto-detects which language is spoken
_STT_LANG = {
    "amharic":   "am-ET",
    "english":   "en-US",
    "bilingual": "am-ET,en-US",
}


def _mulaw_energy(chunk: bytes) -> float:
    """Approximate amplitude energy from raw mulaw bytes.

    In G.711 mu-law: silence bytes cluster near 0x7F (positive) and 0xFF
    (negative).  Distance from those values ≈ signal amplitude (0-127).
    """
    if not chunk:
        return 0.0
    total = 0
    for b in chunk:
        if b & 0x80:          # negative sample — silence near 0xFF
            total += b & 0x7F
        else:                  # positive sample — silence near 0x7F
            total += 0x7F - b
    return total / len(chunk)


# ════════════════════════════════════════════════════════════════════════════
# POST /incoming-call
# ════════════════════════════════════════════════════════════════════════════
@router.post("/incoming-call")
async def incoming_call(request: Request):
    form     = await request.form()
    call_sid = form.get("CallSid", "UNKNOWN")
    caller   = form.get("From", "UNKNOWN")
    to       = form.get("To", "")

    session  = session_manager.create(call_sid, caller)

    # Pre-populate phone from Twilio caller ID — agent should NEVER ask for it
    if caller and caller not in ("UNKNOWN", "anonymous"):
        import re as _re
        digits = _re.sub(r'\D', '', caller)
        if digits.startswith('1') and len(digits) == 11:
            digits = digits[1:]   # strip US country code
        if len(digits) == 10:
            session.set_contact("phone", digits)
            print(f"[CALL] Phone pre-set from caller ID: {digits}")

    # Identify company from the called Twilio number
    company = get_by_number(to) or default_company()
    if company:
        session.company_id = company.id
        session.language   = company.language
        print(f"\n[CALL] Incoming: {caller} → {call_sid} | Company: {company.name}")
    else:
        print(f"\n[CALL] Incoming: {caller} → {call_sid} | No company found")

    twiml = VoiceResponse()

    # Bilingual → show language selection menu (DTMF press 1 / press 2)
    if session.language == "bilingual":
        gather = Gather(
            num_digits=1,
            action=f"{config.BASE_URL}/language-select/{call_sid}",
            method="POST",
            timeout=8,
        )
        company_name = company.name if company else "our office"
        gather.say(
            f"Welcome to {company_name}. "
            "For English, press 1. "
            "For Amharic, press 2.",
            voice="alice",
            language="en-US",
        )
        twiml.append(gather)
        # Timeout fallback — default to English if no key pressed
        twiml.redirect(
            f"{config.BASE_URL}/language-select/{call_sid}",
            method="POST",
        )
    else:
        # Non-bilingual — connect directly to WebSocket
        ws_host    = config.BASE_URL.replace("https://", "").replace("http://", "")
        stream_url = f"wss://{ws_host}/media-stream/{call_sid}"
        connect    = Connect()
        connect.append(Stream(url=stream_url))
        twiml.append(connect)
        print(f"[CALL] Stream URL: {stream_url}")

    return Response(content=str(twiml), media_type="application/xml")


# ════════════════════════════════════════════════════════════════════════════
# POST /language-select/{call_sid}  — receives DTMF digit, sets language
# ════════════════════════════════════════════════════════════════════════════
@router.post("/language-select/{call_sid}")
async def language_select(request: Request, call_sid: str):
    form  = await request.form()
    digit = form.get("Digits", "")   # empty = timeout redirect (default English)

    session = session_manager.get(call_sid)
    if session:
        if digit == "2":
            session.language = "amharic"
            print(f"[IVR] {call_sid} → Amharic selected")
        else:
            session.language = "english"
            print(f"[IVR] {call_sid} → English selected (digit={digit!r})")

    ws_host    = config.BASE_URL.replace("https://", "").replace("http://", "")
    stream_url = f"wss://{ws_host}/media-stream/{call_sid}"

    twiml   = VoiceResponse()
    connect = Connect()
    connect.append(Stream(url=stream_url))
    twiml.append(connect)

    print(f"[IVR] Connecting stream: {stream_url}")
    return Response(content=str(twiml), media_type="application/xml")


# ════════════════════════════════════════════════════════════════════════════
# WS /media-stream/{call_sid}
# ════════════════════════════════════════════════════════════════════════════
@router.websocket("/media-stream/{call_sid}")
async def media_stream(websocket: WebSocket, call_sid: str):
    await websocket.accept()
    print(f"[WS] Connected: {call_sid}")

    session = session_manager.get(call_sid)
    if not session:
        print(f"[WS] No session for {call_sid}")
        await websocket.close()
        return

    # Language is already set from company config in incoming_call
    stt_lang = _STT_LANG.get(session.language, "am-ET")
    print(f"[PIPELINE] Language={session.language} | STT={stt_lang}")

    stream_sid    = None
    audio_buffer  = bytearray()
    silent_chunks = 0
    speech_chunks = 0
    in_speech     = False
    processing    = False     # prevent overlapping STT calls

    async def send_audio(audio_bytes: bytes):
        if audio_bytes and stream_sid:
            await websocket.send_json({
                "event": "media",
                "streamSid": stream_sid,
                "media": {"payload": audio_to_base64(audio_bytes)},
            })

    async def process_utterance(audio: bytes):
        nonlocal processing
        if processing:
            return
        processing = True
        try:
            # ── STEP 1: Google STT ──────────────────────────────────────────
            print(f"[1/4 STT] Sending {len(audio)} bytes → Google STT ({stt_lang})")
            sentence = await google_stt(audio, language=stt_lang)
            if not sentence:
                print("[1/4 STT] No transcript — skipping")
                return
            print(f"[1/4 STT] Caller: {sentence}")
            session.add_user_message(sentence)
            extract_contact_info(session, sentence)

            # ── STEP 2: RAG + STEP 3: LLM (inside generate_response) ───────
            ai_reply = await generate_response(session, sentence)
            session.add_agent_message(ai_reply)
            extract_name_from_reply(session, ai_reply)   # capture name if LLM used it
            print(f"[3/4 LLM] Agent: {ai_reply}")

            # ── STEP 4: Google TTS → send audio ────────────────────────────
            print(f"[4/4 TTS] Converting reply to {session.language} audio")
            await send_audio(text_to_speech(ai_reply, session.language))
        finally:
            processing = False

    # ── Main audio loop ──────────────────────────────────────────────────
    greeting_sent = False
    try:
        async for raw in websocket.iter_text():
            data  = json.loads(raw)
            event = data.get("event")

            if event == "start":
                stream_sid = data.get("streamSid") or data["start"].get("streamSid")
                print(f"[CALL] ▶️  Stream started | streamSid: {stream_sid}")

                if not greeting_sent:
                    greeting_sent = True
                    greeting = await generate_response(session, "", is_greeting=True)
                    session.add_agent_message(greeting)
                    print(f"[AI]  🤖 Greeting: {greeting}")
                    await send_audio(text_to_speech(greeting, session.language))

            elif event == "media":
                chunk  = base64.b64decode(data["media"]["payload"])
                energy = _mulaw_energy(chunk)

                if energy > SILENCE_THRESHOLD:
                    # ── Active speech ────────────────────────────
                    in_speech = True
                    silent_chunks = 0
                    speech_chunks += 1
                    audio_buffer.extend(chunk)

                    # Safety cap — avoid infinite buffering
                    if speech_chunks >= MAX_BUFFER_CHUNKS:
                        asyncio.create_task(process_utterance(bytes(audio_buffer)))
                        audio_buffer.clear()
                        silent_chunks = 0
                        speech_chunks = 0
                        in_speech = False

                elif in_speech:
                    # ── Silence after speech ─────────────────────
                    audio_buffer.extend(chunk)   # include trailing silence
                    silent_chunks += 1

                    if silent_chunks >= SILENCE_CHUNKS:
                        # End of utterance
                        if speech_chunks >= MIN_SPEECH_CHUNKS:
                            asyncio.create_task(
                                process_utterance(bytes(audio_buffer))
                            )
                        audio_buffer.clear()
                        silent_chunks = 0
                        speech_chunks = 0
                        in_speech = False

            elif event == "stop":
                print(f"[CALL] 📵 Ended: {call_sid}")
                break

    except WebSocketDisconnect:
        print(f"[WS] Disconnected: {call_sid}")

    finally:
        if not session.ghl_sent:
            await send_to_ghl(session)
        session_manager.delete(call_sid)
        print(f"[DONE] ✅ {call_sid} | {session.summary()}")
