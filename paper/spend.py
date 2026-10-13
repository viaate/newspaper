"""What the paper's API calls cost, worked out from each call's own token counts.

Neither key can report its credit balance, so the paper keeps a ledger in data/ and,
given the balance you saw on a date ([spend] in config.toml), says what's left.
"""

import json
from datetime import date, timedelta

# USD per million tokens (Claude Haiku 5.5 for prompts up to 100K tokens; Gemini 3.1
# Flash Image), from each provider's pricing page. Override under [spend.rates].
RATES = {
    "anthropic": {"input": 0.10, "output": 0.50, "input_long": 0.50, "output_long": 2.50},
    "gemini": {"input": 0.50, "output_text": 3.00, "output_image": 60.00},
}


def _path(cfg):
    return cfg["data_dir"] / "spend.json"


def _rates(cfg, service):
    return {**RATES[service], **cfg.get("spend", {}).get("rates", {}).get(service, {})}


def record(cfg, service, what, usd):
    path = _path(cfg)
    entries = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    entries.append({"date": date.today().isoformat(), "service": service, "what": what, "usd": round(usd, 6)})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, indent=1), encoding="utf-8")


def record_claude(cfg, what, usage):
    r = _rates(cfg, "anthropic")
    prompt = usage.input_tokens + (usage.cache_read_input_tokens or 0) + (usage.cache_creation_input_tokens or 0)
    long = "_long" if prompt > 100_000 else ""
    usd = (usage.input_tokens * r["input" + long] + usage.output_tokens * r["output" + long]
           + (usage.cache_read_input_tokens or 0) * r["input" + long] * 0.1
           + (usage.cache_creation_input_tokens or 0) * r["input" + long] * 1.25) / 1e6
    record(cfg, "anthropic", what, usd)


def record_gemini(cfg, what, usage):
    """`usage` is the response's usageMetadata."""
    r = _rates(cfg, "gemini")
    out = usage.get("candidatesTokenCount", 0)
    image = sum(d.get("tokenCount", 0) for d in usage.get("candidatesTokensDetails", []) if d.get("modality") == "IMAGE")
    text = out - image + usage.get("thoughtsTokenCount", 0)
    usd = (usage.get("promptTokenCount", 0) * r["input"] + image * r["output_image"] + text * r["output_text"]) / 1e6
    record(cfg, "gemini", what, usd)


def summary(cfg, today=None):
    """Per service: today, the last 30 days, and credit left if a balance is set."""
    today = today or date.today()
    path = _path(cfg)
    entries = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    s = cfg.get("spend", {})
    since = s.get("since", "")
    month_ago = (today - timedelta(days=30)).isoformat()
    out = []
    for service, name in (("anthropic", "Claude API"), ("gemini", "Gemini API")):
        mine = [e for e in entries if e["service"] == service]
        credit = s.get(f"{service}_credit") or 0
        row = {
            "name": name,
            "today": sum(e["usd"] for e in mine if e["date"] == today.isoformat()),
            "month": sum(e["usd"] for e in mine if e["date"] > month_ago),
            "credit": credit or None,
            "left": None,
        }
        if credit:
            start = s.get(f"{service}_since", since)  # the day that balance was read
            row["left"] = credit - sum(e["usd"] for e in mine if e["date"] >= start)
        out.append(row)
    return out


def mark(cfg):
    """Where the ledger ends now; pass it to since() after a build for that build's cost."""
    path = _path(cfg)
    return len(json.loads(path.read_text(encoding="utf-8"))) if path.exists() else 0


def since(cfg, start):
    path = _path(cfg)
    entries = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    return {service: sum(e["usd"] for e in entries[start:] if e["service"] == service)
            for service in ("anthropic", "gemini")}
