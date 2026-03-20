"""
start_tunnel.py — Start ngrok tunnel and update BASE_URL in .env
Run: python start_tunnel.py
"""
import os
import re
from dotenv import load_dotenv
from pyngrok import ngrok, conf

load_dotenv()

# Set auth token if provided
auth_token = os.getenv("NGROK_AUTHTOKEN", "") or os.getenv("NGROK_AUTH_TOKEN", "")
if auth_token:
    conf.get_default().auth_token = auth_token

print("Starting ngrok tunnel on port 8000...")
tunnel = ngrok.connect(8000, "http")
public_url = tunnel.public_url

# Ensure https
if public_url.startswith("http://"):
    public_url = public_url.replace("http://", "https://", 1)

print(f"\n✅ Tunnel URL: {public_url}")
print(f"\n📋 Copy this to your .env:")
print(f"   BASE_URL={public_url}")
print(f"\n📋 Copy this to Twilio webhook:")
print(f"   {public_url}/incoming-call")
print(f"\n⏳ Tunnel is running... press Ctrl+C to stop")

# Update .env automatically
env_path = ".env"
with open(env_path, "r", encoding="utf-8") as f:
    content = f.read()

content = re.sub(r"BASE_URL=.*", f"BASE_URL={public_url}", content)

with open(env_path, "w", encoding="utf-8") as f:
    f.write(content)

print(f"✅ BASE_URL updated in .env automatically")

try:
    input()
except KeyboardInterrupt:
    pass
finally:
    print("\nTunnel stopped.")
    ngrok.kill()
