"""test_ghl.py — Send a test payload to GHL webhook to create mapping reference."""
import httpx
from dotenv import load_dotenv
import os

load_dotenv()

url = os.getenv("GHL_WEBHOOK_URL", "")
if not url:
    print("ERROR: GHL_WEBHOOK_URL not set in .env")
    exit(1)

print(f"Sending test to: {url}")

payload = {
    "firstName":      "Test",
    "phone":          "+12025551234",
    "caller":         "+12025551234",
    "source":         "Amharic Voice Agent",
    "language":       "amharic",
    "service":        "Financial Services",
    "callSid":        "TEST123",
    "transcript":     "ስለ ታክስ አገልግሎት ጠየቁ",
    "summary":        "Caller asked about tax services",
    "appointmentDay": "Monday",
    "tags":           "voice-agent,amharic,amazon-consulting",
}

r = httpx.post(url, json=payload, timeout=10)
print(f"Status: {r.status_code}")
print(f"Response: {r.text}")
