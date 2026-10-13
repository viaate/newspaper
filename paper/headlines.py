"""Every headline the paper has run, so no title idea is used twice.

The writer sees the list and is told to find a new angle; after it writes, the front-page
headline is checked against every earlier one, and one that's too close is rewritten.
"""

import json
import re
from difflib import SequenceMatcher

from . import spend

FILLER = set("a an the and or but so of to in on at for with by from is are was were be been it its this that "
             "your you today still just now up down out off over under".split())


def _path(cfg):
    return cfg["data_dir"] / "headlines.json"


def load(cfg, today):
    """Earlier days' titles, newest first (today's own entry left out, since it may be rebuilt)."""
    path = _path(cfg)
    if path.exists():
        rows = json.loads(path.read_text(encoding="utf-8"))
    else:  # first run: start from the issues already in the archive
        issues = json.loads((cfg["data_dir"] / "archive.json").read_text(encoding="utf-8")).get("issues", {}) \
            if (cfg["data_dir"] / "archive.json").exists() else {}
        rows = [{"date": d, "headline": i.get("headline", "")} for d, i in issues.items() if i.get("headline")]
    return sorted((r for r in rows if r["date"] != today.isoformat()), key=lambda r: r["date"], reverse=True)


def save(cfg, today, edition):
    path = _path(cfg)
    rows = [r for r in load(cfg, today)]
    rows.append({"date": today.isoformat(), "headline": edition.get("headline", ""), "deck": edition.get("deck", ""),
                 "comic": (edition.get("comic") or {}).get("title", ""), "dear": (edition.get("dear") or {}).get("headline", "")})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(rows, key=lambda r: r["date"]), indent=1), encoding="utf-8")


def _words(text):
    return {w for w in re.findall(r"[a-z0-9.]+", text.lower()) if w not in FILLER}


def too_close(headline, earlier):
    """The earlier headline this one repeats (same wording, or mostly the same words), or None."""
    mine, words = headline.lower().strip(), _words(headline)
    for old in earlier:
        theirs = old.lower().strip()
        if not theirs:
            continue
        shared = len(words & _words(old)) / max(1, min(len(words), len(_words(old))))
        if mine == theirs or SequenceMatcher(None, mine, theirs).ratio() >= 0.72 or shared >= 0.6:
            return old
    return None


def rewrite(cfg, client, model, edition, earlier, clash):
    """A fresh headline on the same story: three tries in one short call, the first that
    passes the check wins; the original stays if none do or the call fails."""
    prompt = (
        f"Today's front-page headline for {cfg['paper']['name']} was:\n{edition['headline']}\n\n"
        f"It's too close to one that already ran: {clash}\n\n"
        f"Today's story, from the lead:\n{' '.join(edition.get('lead', []))[:1200]}\n\n"
        "Headlines that already ran (never reuse their wording, structure or angle):\n"
        + "\n".join(f"- {h}" for h in earlier[:60])
        + "\n\nWrite three new front-page headlines for today, each from a different angle on what's new today "
          "(a different class, deadline, number or event), each at most 9 words, in sentence case. Never invent or "
          "round a number. Reply with the three headlines only, one per line."
    )
    try:
        reply = client.messages.create(model=model, max_tokens=2000, output_config={"effort": "low"},
                                       messages=[{"role": "user", "content": prompt}])
        spend.record_claude(cfg, "headline", reply.usage)
        text = next((b.text for b in reply.content if b.type == "text"), "")
        for line in text.splitlines():
            option = re.sub(r"^\s*(\d+[.)]|[-*•])\s*", "", line).strip().strip('"').strip()
            if option and not too_close(option, earlier):
                return option
    except Exception as e:  # keep the paper going with the first headline
        print(f"headline: couldn't rewrite: {e}")
    return edition["headline"]
