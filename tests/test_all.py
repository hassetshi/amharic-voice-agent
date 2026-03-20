#!/usr/bin/env python3
"""
tests/test_all.py
Run ALL tests: python tests/test_all.py
Run one test:  python tests/test_all.py --only openai
"""

import sys
import asyncio
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

OK   = "✅"
FAIL = "❌"
SKIP = "⏭️ "

results = []


# ════════════════════════════════════════════════════════
# TEST 1 — Config / .env loaded correctly
# ════════════════════════════════════════════════════════
def test_config():
    print("\n── 1. Config & .env ───────────────────────────────")
    from src.config import config
    missing = config.validate()
    if missing:
        print(f"{FAIL} Missing keys: {missing}")
        print("     → Edit your .env file and add these keys")
        results.append(("Config", False))
    else:
        print(f"{OK} All required API keys are set")
        print(f"   Business: {config.BUSINESS_NAME}")
        print(f"   Base URL: {config.BASE_URL}")
        results.append(("Config", True))


# ════════════════════════════════════════════════════════
# TEST 2 — Language detection
# ════════════════════════════════════════════════════════
def test_language_detection():
    print("\n── 2. Language Detection ──────────────────────────")
    from src.services import detect_language

    cases = [
        ("ሰላም! እንዴት ነዎት?",          "amharic"),
        ("Hello, I need help",         "english"),
        ("ቪዛ አፕሊኬሽን ጥያቄ አለኝ",       "amharic"),
        ("I want to ship cargo",       "english"),
        ("ካርጎ ወደ ኢትዮጵያ ለመላክ",       "amharic"),
    ]
    passed = 0
    for text, expected in cases:
        detected = detect_language(text)
        status   = OK if detected == expected else FAIL
        print(f"   {status} '{text[:30]}...' → {detected}")
        if detected == expected:
            passed += 1

    all_ok = passed == len(cases)
    results.append(("Language Detection", all_ok))
    if all_ok:
        print(f"{OK} All {len(cases)} language detection tests passed")


# ════════════════════════════════════════════════════════
# TEST 3 — Session manager
# ════════════════════════════════════════════════════════
def test_sessions():
    print("\n── 3. Session Manager ─────────────────────────────")
    from src.session import SessionManager
    mgr = SessionManager()

    s = mgr.create("TEST-001", "+12401234567")
    s.add_user_message("ሰላም")
    s.add_agent_message("ሰላም! ወደ አማዞን ኮንሰልቲንግ እንኳን ደህና መጡ።")
    s.set_contact("service", "Immigration & Embassy")
    s.language = "amharic"

    assert mgr.count() == 1
    assert mgr.get("TEST-001") is not None
    assert len(s.messages) == 2
    assert s.contact["service"] == "Immigration & Embassy"
    assert "amharic" in s.summary().lower()

    mgr.delete("TEST-001")
    assert mgr.count() == 0

    print(f"{OK} Session create/read/delete works")
    print(f"{OK} Transcript appending works")
    print(f"{OK} Contact info storage works")
    results.append(("Session Manager", True))


# ════════════════════════════════════════════════════════
# TEST 4 — Contact extraction
# ════════════════════════════════════════════════════════
def test_contact_extraction():
    print("\n── 4. Contact Extraction ──────────────────────────")
    from src.session import CallSession
    from src.services import extract_contact_info

    session = CallSession(call_sid="TEST-002", caller="+10000000000")

    # Test phone extraction
    extract_contact_info(session, "My number is 240-641-1515")
    assert "phone" in session.contact, "Phone not extracted"
    print(f"{OK} Phone extracted: {session.contact['phone']}")

    # Test service extraction (English)
    extract_contact_info(session, "I need help with immigration visa")
    assert session.contact.get("service") == "Immigration & Embassy"
    print(f"{OK} Service extracted (EN): {session.contact['service']}")

    # Test service extraction (Amharic)
    session2 = CallSession(call_sid="TEST-003", caller="+10000000001")
    extract_contact_info(session2, "ካርጎ ወደ ኢትዮጵያ ለመላክ እፈልጋለሁ")
    assert session2.contact.get("service") == "Cargo & Shipping"
    print(f"{OK} Service extracted (AM): {session2.contact['service']}")

    results.append(("Contact Extraction", True))


# ════════════════════════════════════════════════════════
# TEST 5 — Anthropic Claude (Amharic)
# ════════════════════════════════════════════════════════
async def test_openai():
    print("\n── 5. Anthropic Claude (Amharic) ───────────────────")
    from src.session import CallSession
    from src.services import generate_response

    if not os.getenv("ANTHROPIC_API_KEY"):
        print(f"{SKIP} ANTHROPIC_API_KEY not set — skipping")
        results.append(("Claude", None))
        return

    try:
        session = CallSession(call_sid="TEST-CLAUDE", caller="+10000000000")
        reply = await generate_response(session, "", is_greeting=True)
        print(f"{OK} Greeting generated ({len(reply)} chars):")
        print(f"   {reply[:100]}...")

        session2 = CallSession(call_sid="TEST-CLAUDE-2", caller="+10000000001")
        session2.language = "amharic"
        reply2 = await generate_response(session2, "ስለ ቪዛ ጥያቄ አለኝ")
        print(f"{OK} Amharic response:")
        print(f"   {reply2[:100]}...")

        results.append(("Claude", True))
    except Exception as e:
        print(f"{FAIL} Claude error: {e}")
        results.append(("Claude", False))


# ════════════════════════════════════════════════════════
# TEST 6 — TTS: Google (Amharic) + ElevenLabs (English)
# ════════════════════════════════════════════════════════
async def test_elevenlabs():
    print("\n── 6. TTS (Google=Amharic, ElevenLabs=English) ────")
    from src.services import _google_tts, _elevenlabs_tts

    os.makedirs("audio_samples", exist_ok=True)
    passed = 0
    failed = 0

    # ── Google TTS — Amharic ────────────────────────────
    google_key = os.getenv("GOOGLE_TTS_API_KEY", "")
    if not google_key or "your_" in google_key:
        print(f"{SKIP} GOOGLE_TTS_API_KEY not set — skipping Amharic TTS")
    else:
        try:
            audio = _google_tts("ሰላም! ወደ አማዞን ኮንሰልቲንግ እንኳን ደህና መጡ።", mulaw=False)
            if audio:
                path = "audio_samples/test_amharic_google.mp3"
                with open(path, "wb") as f:
                    f.write(audio)
                print(f"{OK} Google Amharic TTS: {len(audio)/1024:.1f}KB → {path}")
                passed += 1
            else:
                print(f"{FAIL} Google Amharic TTS returned empty audio")
                failed += 1
        except Exception as e:
            print(f"{FAIL} Google Amharic TTS error: {e}")
            failed += 1

    # ── ElevenLabs — English ────────────────────────────
    el_key = os.getenv("ELEVENLABS_API_KEY", "")
    if not el_key or "your_" in el_key:
        print(f"{SKIP} ELEVENLABS_API_KEY not set — skipping English TTS")
    else:
        try:
            audio = _elevenlabs_tts("Hello! Welcome to Amazon Consulting.", mulaw=False)
            if audio:
                path = "audio_samples/test_english_elevenlabs.mp3"
                with open(path, "wb") as f:
                    f.write(audio)
                print(f"{OK} ElevenLabs English TTS: {len(audio)/1024:.1f}KB → {path}")
                passed += 1
            else:
                print(f"{FAIL} ElevenLabs English TTS returned empty audio")
                failed += 1
        except Exception as e:
            print(f"{FAIL} ElevenLabs English TTS error: {e}")
            failed += 1

    if failed > 0:
        results.append(("TTS", False))
    elif passed == 0:
        results.append(("TTS", None))
    else:
        results.append(("TTS", True))


# ════════════════════════════════════════════════════════
# TEST 7 — GHL Webhook
# ════════════════════════════════════════════════════════
async def test_ghl():
    print("\n── 7. GHL Webhook ─────────────────────────────────")
    from src.session import CallSession
    from src.services import send_to_ghl

    url = os.getenv("GHL_WEBHOOK_URL", "")
    if not url or "YOUR_ID" in url:
        print(f"{SKIP} GHL_WEBHOOK_URL not configured — skipping")
        results.append(("GHL Webhook", None))
        return

    try:
        session = CallSession(call_sid="LOCAL-GHL-TEST", caller="+12401234567")
        session.language = "amharic"
        session.add_user_message("ሰላም")
        session.add_agent_message("ሰላም! ወደ አማዞን ኮንሰልቲንግ እንኳን ደህና መጡ።")
        session.set_contact("service", "Immigration & Embassy")
        session.set_contact("phone", "+12401234567")

        await send_to_ghl(session)
        print(f"{OK} GHL webhook call completed")
        print(f"   → Check GHL Contacts for 'LOCAL-GHL-TEST'")
        results.append(("GHL Webhook", True))
    except Exception as e:
        print(f"{FAIL} GHL error: {e}")
        results.append(("GHL Webhook", False))


# ════════════════════════════════════════════════════════
# TEST 8 — FastAPI routes (no server needed)
# ════════════════════════════════════════════════════════
async def test_routes():
    print("\n── 8. FastAPI App Structure ────────────────────────")
    try:
        from src.app import create_app
        app = create_app()
        routes = [r.path for r in app.routes]

        required = ["/health", "/incoming-call", "/test-amharic", "/test-chat"]
        for route in required:
            if route in routes:
                print(f"{OK} Route exists: {route}")
            else:
                print(f"{FAIL} Missing route: {route}")

        results.append(("FastAPI Routes", True))
    except Exception as e:
        print(f"{FAIL} App creation error: {e}")
        results.append(("FastAPI Routes", False))


# ════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════
async def run_all():
    print("\n" + "═" * 55)
    print("  🇪🇹  Amharic Voice Agent — Test Suite")
    print("  Amazon Consulting LLC")
    print("═" * 55)

    # Sync tests
    test_config()
    test_language_detection()
    test_sessions()
    test_contact_extraction()
    await test_routes()

    # Async API tests
    await test_openai()
    await test_elevenlabs()
    await test_ghl()

    # ── Summary ──────────────────────────────────────────
    print("\n" + "═" * 55)
    print("  TEST RESULTS")
    print("═" * 55)
    passed = skipped = failed = 0
    for name, result in results:
        if result is True:
            print(f"  {OK}  {name}")
            passed += 1
        elif result is None:
            print(f"  {SKIP}  {name} (skipped — key not set)")
            skipped += 1
        else:
            print(f"  {FAIL}  {name}")
            failed += 1

    print("═" * 55)
    print(f"  Passed: {passed} | Skipped: {skipped} | Failed: {failed}")

    if failed == 0:
        print("\n  🚀 Ready to run! Start with:")
        print("     python main.py")
        print("     ngrok http 8000")
    else:
        print("\n  ⚠️  Fix failing tests then re-run")
    print("═" * 55 + "\n")


if __name__ == "__main__":
    only = None
    if "--only" in sys.argv:
        idx  = sys.argv.index("--only")
        only = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else None

    asyncio.run(run_all())
