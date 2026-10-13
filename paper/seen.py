"""Every news story the paper has printed, so none runs twice.

Candidates are dropped before the writer sees them when their link has run before, or when
their title reports the same news as one printed in the last two weeks (another outlet's
take on yesterday's story). The writer also sees recent headlines, for follow-ups.
"""

import json
import re
from datetime import date
from difflib import SequenceMatcher

from .headlines import FILLER

KEEP_DAYS = 60     # news is at most a week old, so this is plenty for links
TITLE_DAYS = 14


def _path(cfg):
    return cfg["data_dir"] / "stories.json"


def load(cfg, today):
    """Stories printed on earlier days, newest first (today's left out, since it may be rebuilt)."""
    path = _path(cfg)
    rows = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    return sorted((r for r in rows if r["date"] != today.isoformat()
                   and (today - date.fromisoformat(r["date"])).days <= KEEP_DAYS),
                  key=lambda r: r["date"], reverse=True)


def save(cfg, today, edition, sections):
    """Add today's printed stories (by link, and by the feed's own title)."""
    by_url = {n["url"]: n for items in sections.values() for n in items}
    ran = [s for key in ("tech", "local", "world") for s in edition.get(key) or []]
    if edition.get("feature"):
        ran.append(edition["feature"])
    rows = load(cfg, today) + [{
        "date": today.isoformat(), "url": s["url"], "headline": s["headline"],
        "title": by_url.get(s["url"], {}).get("title") or s["headline"],
    } for s in ran if s.get("url") or s.get("headline")]
    path = _path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(rows, key=lambda r: r["date"]), indent=1), encoding="utf-8")


def _words(text):
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in FILLER and len(w) > 2}


def same_story(a, b):
    """Two titles reporting the same news: nearly the same wording, or nearly all the same words."""
    a, b = a.lower().strip(), b.lower().strip()
    if not a or not b:
        return False
    wa, wb = _words(a), _words(b)
    shared = len(wa & wb)
    if a == b or (shared >= 4 and shared / max(1, min(len(wa), len(wb))) >= 0.75):
        return True
    m = SequenceMatcher(None, a, b)
    return m.real_quick_ratio() >= 0.85 and m.quick_ratio() >= 0.85 and m.ratio() >= 0.85


def unseen(sections, printed, today):
    """Each section's candidates, minus the ones that have already run."""
    urls = {r["url"] for r in printed if r.get("url")}
    titles = [t for r in printed if (today - date.fromisoformat(r["date"])).days <= TITLE_DAYS
              for t in {r["title"], r["headline"]}]
    return {name: [n for n in items if n["url"] not in urls and not any(same_story(n["title"], t) for t in titles)]
            for name, items in sections.items()}
