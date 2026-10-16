"""Every school topic the paper's writing has already talked about, so each gets said once.

The writer lists the topics its prose covered (a test, an assignment, an email, an event);
later editions see that list and leave those topics out of the headline, lead, comic and
other writing unless something new has happened. Tables (Today, This Week, Grade Watch)
still list everything; they're reference, not news.
"""

import json
from datetime import date

KEEP_DAYS = 30


def _path(cfg):
    return cfg["data_dir"] / "covered.json"


def load(cfg, today):
    """Earlier days' topics, newest first (today's left out, since the paper may be rebuilt)."""
    path = _path(cfg)
    rows = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    return sorted((r for r in rows if r["date"] != today.isoformat()
                   and (today - date.fromisoformat(r["date"])).days <= KEEP_DAYS),
                  key=lambda r: r["date"], reverse=True)


def save(cfg, today, edition):
    topics = [t.strip() for t in edition.get("topics") or [] if t and t.strip()]
    rows = load(cfg, today) + ([{"date": today.isoformat(), "topics": topics}] if topics else [])
    path = _path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(rows, key=lambda r: r["date"]), indent=1), encoding="utf-8")


def for_writer(rows):
    """[{"topic", "covered_on"}] for the facts, newest first."""
    return [{"topic": t, "covered_on": r["date"]} for r in rows for t in r["topics"]][:150]
