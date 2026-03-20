# 🇪🇹 Amazon Consulting — Amharic Voice Agent

Bilingual English + Amharic voice agent for Amazon Consulting LLC  
Silver Spring, MD | (240) 641-1515 | dmvamazon.com

---

## Project Structure

```
amharic-voice-agent/
├── main.py                    ← Entry point — run this
├── requirements.txt           ← Python deps
├── .env.example               ← Copy to .env and fill keys
├── .env                       ← YOUR keys (never commit!)
│
├── src/
│   ├── app.py                 ← FastAPI factory
│   ├── config.py              ← All env vars + validation
│   ├── prompts.py             ← Amharic + English scripts
│   ├── session.py             ← Call session state manager
│   ├── services.py            ← STT / LLM / TTS / GHL
│   └── routes/
│       ├── health_routes.py   ← /health /test-amharic /test-chat
│       └── call_routes.py     ← /incoming-call + WebSocket
│
├── tests/
│   └── test_all.py            ← Full test suite
│
├── audio_samples/             ← Generated MP3 test files
└── .vscode/
    ├── launch.json            ← Debug configs
    └── settings.json          ← Python settings
```

---

## Setup in VS Code — Step by Step

### Step 1 — Open Project
```bash
# Open VS Code in the project folder
code amharic-voice-agent
```
Or: File → Open Folder → select `amharic-voice-agent`

---

### Step 2 — Create Virtual Environment
Open VS Code terminal (`Ctrl+`` ` or Terminal → New Terminal):
```bash
# Create venv
python3 -m venv venv

# Activate (Mac/Linux)
source venv/bin/activate

# Activate (Windows)
venv\Scripts\activate

# You should see (venv) in your terminal prompt
```

---

### Step 3 — Install Dependencies
```bash
pip install -r requirements.txt
```
Takes 2-3 minutes. You'll see packages installing.

---

### Step 4 — Set Up API Keys
```bash
# Copy the template
cp .env.example .env

# Open .env and fill in your keys
code .env
```

Fill in these keys (get them from each service):
| Key | Where to get it |
|-----|----------------|
| `DEEPGRAM_API_KEY` | console.deepgram.com → API Keys |
| `OPENAI_API_KEY` | platform.openai.com → API Keys |
| `ELEVENLABS_API_KEY` | elevenlabs.io → Profile → API Key |
| `ELEVENLABS_VOICE_ID` | ElevenLabs → Voice Library → click voice |
| `TWILIO_ACCOUNT_SID` | console.twilio.com → Account Info |
| `TWILIO_AUTH_TOKEN` | console.twilio.com → Account Info |
| `GHL_WEBHOOK_URL` | GHL → Automations → Inbound Webhook |
| `BASE_URL` | Your ngrok URL (see Step 7) |

---

### Step 5 — Run Tests First
```bash
python tests/test_all.py
```

Expected output:
```
✅ Config & .env
✅ Language Detection
✅ Session Manager  
✅ Contact Extraction
✅ FastAPI Routes
✅ OpenAI (if key set)
✅ ElevenLabs (if key set) → saves audio_samples/test_greeting.mp3
⏭️  GHL Webhook (until you set the URL)
```

🎵 **Open `audio_samples/test_greeting.mp3`** to hear your Amharic voice!

---

### Step 6 — Run the Server
**Option A — VS Code Debug (recommended):**
Press `F5` → select **▶️ Run Voice Agent**

**Option B — Terminal:**
```bash
python main.py
```

Server starts at: `http://localhost:8000`

---

### Step 7 — Test Locally (No Phone Needed!)

Open these in your browser:

| URL | What it does |
|-----|-------------|
| `http://localhost:8000/health` | Check API key status |
| `http://localhost:8000/test-amharic` | **▶️ Plays Amharic greeting audio** |
| `http://localhost:8000/test-financial` | Plays Financial Services Amharic |
| `http://localhost:8000/test-immigration` | Plays Immigration Amharic |
| `http://localhost:8000/test-chat?message=ሰላም` | Test AI with Amharic text |
| `http://localhost:8000/test-chat?message=I need a visa` | Test AI with English |

---

### Step 8 — Connect to Real Phone (ngrok + Twilio)

```bash
# Install ngrok: https://ngrok.com/download
# Run in a NEW terminal (keep main.py running):
ngrok http 8000

# Copy the https URL shown, e.g.:
# https://abc123.ngrok.io

# Update your .env:
BASE_URL=https://abc123.ngrok.io

# Restart main.py after updating .env
```

Then in Twilio dashboard:
1. Phone Numbers → your number → Voice webhook
2. Set URL to: `https://abc123.ngrok.io/incoming-call`
3. Method: POST → Save

**Call your Twilio number → agent answers in Amharic + English! 🎉**

---

## Testing Checklist

- [ ] `python tests/test_all.py` — all tests pass
- [ ] Open `/test-amharic` in browser — hear the voice
- [ ] Open `/test-chat?message=ሰላም` — see Amharic AI response  
- [ ] Open `/test-chat?message=I need immigration help` — see English response
- [ ] Call Twilio number — agent answers
- [ ] Speak in Amharic — agent responds in Amharic
- [ ] Check GHL → Contacts after call — new contact appears

---

## Cost Estimate

| Service | Plan | Monthly |
|---------|------|---------|
| Deepgram Nova-2 | Pay-as-go | ~$2 |
| OpenAI GPT-4o | Pay-as-go | ~$3 |
| ElevenLabs | Starter $5 | $5 |
| Twilio | Pay-as-go | ~$2 |
| Railway (hosting) | Starter | $5 |
| **Total** | | **~$17/mo** |
