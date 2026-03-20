"""
src/session.py — In-memory call session manager
"""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class CallSession:
    call_sid:    str
    caller:      str
    started_at:  str = field(default_factory=lambda: datetime.now().isoformat())
    language:    str = "amharic"
    company_id:  str = ""                 # set from Twilio 'To' number lookup
    messages:    list = field(default_factory=list)   # conversation history
    transcript:  list = field(default_factory=list)   # Full call transcript
    contact:     dict = field(default_factory=dict)   # Collected CRM data
    ghl_sent:    bool = False

    def add_user_message(self, text: str):
        self.messages.append({"role": "user", "content": text})
        self.transcript.append({"role": "caller", "text": text,
                                 "time": datetime.now().isoformat()})

    def add_agent_message(self, text: str):
        self.messages.append({"role": "assistant", "content": text})
        self.transcript.append({"role": "agent", "text": text,
                                 "time": datetime.now().isoformat()})

    def set_contact(self, key: str, value: str):
        if value and key not in self.contact:
            self.contact[key] = value

    def full_transcript_text(self) -> str:
        return "\n".join(
            f"{t['role'].upper()}: {t['text']}"
            for t in self.transcript
        )

    def summary(self) -> str:
        service = self.contact.get("service", "General Inquiry")
        lang    = self.language
        name    = self.contact.get("name", "Unknown")
        return f"[{lang.upper()}] {name} called about: {service}"


class SessionManager:
    """Thread-safe in-memory session store."""

    def __init__(self):
        self._sessions: dict[str, CallSession] = {}

    def create(self, call_sid: str, caller: str) -> CallSession:
        session = CallSession(call_sid=call_sid, caller=caller)
        self._sessions[call_sid] = session
        print(f"[SESSION] Created: {call_sid} | Caller: {caller}")
        return session

    def get(self, call_sid: str) -> Optional[CallSession]:
        return self._sessions.get(call_sid)

    def delete(self, call_sid: str):
        self._sessions.pop(call_sid, None)
        print(f"[SESSION] Closed: {call_sid}")

    def count(self) -> int:
        return len(self._sessions)

    def list_ids(self) -> list[str]:
        return list(self._sessions.keys())


# Global singleton
session_manager = SessionManager()
