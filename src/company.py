"""
src/company.py — Multi-company support
Each company lives in companies/{id}/config.json + knowledge.txt
The agent picks the right company based on the Twilio 'To' phone number.
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

COMPANIES_DIR = Path(__file__).parent.parent / "companies"


@dataclass
class Company:
    id:               str
    name:             str
    phone:            str
    address:          str
    website:          str
    hours:            str
    language:         str          # "amharic" | "english" | "bilingual"
    twilio_numbers:   list[str]
    ghl_webhook_url:  str
    greeting_amharic: str
    greeting_english: str
    knowledge:        str = ""     # full text of knowledge.txt


# ── Load all companies at startup ────────────────────────────────────────────
_registry: dict[str, Company] = {}      # company_id → Company
_number_map: dict[str, Company] = {}    # twilio_number → Company


def _load_all():
    if not COMPANIES_DIR.exists():
        return
    for company_dir in COMPANIES_DIR.iterdir():
        if not company_dir.is_dir():
            continue
        cfg_path = company_dir / "config.json"
        if not cfg_path.exists():
            continue
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))

            # Read knowledge base
            knowledge = ""
            kb_path = company_dir / "knowledge.txt"
            if kb_path.exists():
                knowledge = kb_path.read_text(encoding="utf-8")

            # Override ghl_webhook_url from env if set
            env_key = f"GHL_WEBHOOK_URL_{cfg['id'].upper()}"
            ghl_url  = os.getenv(env_key) or cfg.get("ghl_webhook_url", "") or os.getenv("GHL_WEBHOOK_URL", "")

            company = Company(
                id               = cfg["id"],
                name             = cfg["name"],
                phone            = cfg["phone"],
                address          = cfg["address"],
                website          = cfg.get("website", ""),
                hours            = cfg["hours"],
                language         = cfg.get("language", "amharic"),
                twilio_numbers   = cfg.get("twilio_numbers", []),
                ghl_webhook_url  = ghl_url,
                greeting_amharic = cfg.get("greeting_amharic", ""),
                greeting_english = cfg.get("greeting_english", ""),
                knowledge        = knowledge,
            )
            _registry[company.id] = company
            for number in company.twilio_numbers:
                _number_map[number] = company

            print(f"[COMPANY] Loaded: {company.name} | numbers: {company.twilio_numbers}")
        except Exception as e:
            print(f"[COMPANY] Failed to load {company_dir.name}: {e}")


def get_by_number(twilio_to: str) -> Company | None:
    """Return the Company that owns this Twilio 'To' number, or None."""
    return _number_map.get(twilio_to)


def get_by_id(company_id: str) -> Company | None:
    return _registry.get(company_id)


def default_company() -> Company | None:
    """Return the first loaded company as a fallback."""
    return next(iter(_registry.values()), None)


# Load on import
_load_all()
