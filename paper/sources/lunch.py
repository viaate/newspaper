"""Today's school lunch, read from the Pembroke Hill dining page.

The page has a panel per campus (id "ward-parkway" or "wornall"), day buttons labeled like
"Tue 10/13" that point at a day panel, and in each day either a "No School" card or station
cards (a badge such as "Flavor & Fav" over a list of dishes).
"""

import re
from datetime import date

import requests
from bs4 import BeautifulSoup

UA = {"User-Agent": "Mozilla/5.0 (newspaper bot; personal use)"}
DAY_PANEL = re.compile(r"setDay\('[\w-]+',\s*'([\w-]+)'")


def _date(label, today):
    m = re.search(r"(\d{1,2})/(\d{1,2})", label)
    if not m:
        return None
    month, day = int(m.group(1)), int(m.group(2))
    # The page has no year; pick the one that puts the date nearest today.
    year = today.year + (1 if month < today.month - 6 else -1 if month > today.month + 6 else 0)
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _text(el):
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip()


def fetch(cfg, today):
    """{"no_school", "note", "stations": [{"name", "items", "featured"}]}, or None if not posted."""
    settings = cfg.get("lunch", {})
    if not settings.get("url"):
        return None
    r = requests.get(settings["url"], headers=UA, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    campus = soup.find(id=settings.get("campus", "ward-parkway"))
    if campus is None:
        raise ValueError(f"no {settings.get('campus')!r} campus on the lunch page")

    for button in campus.select("button.day-btn"):
        panel_id = DAY_PANEL.search(button.get("onclick", ""))
        if not panel_id or _date(_text(button), today) != today:
            continue
        panel = soup.find(id=panel_id.group(1))
        if panel is None:
            return None
        closed = panel.select_one(".no-school-card")
        if closed:
            return {"no_school": True, "note": _text(closed).lstrip("🏫").strip(), "stations": []}
        stations = []
        for card in panel.select(".station-card"):
            badge = card.select_one(".station-badge")
            items = [_text(li) for li in card.select(".items-list li")]
            if items:
                stations.append({
                    "name": _text(badge) if badge else "",
                    "items": items,
                    "featured": [_text(s) for s in card.select(".items-list li strong")],
                })
        return {"no_school": False, "note": "", "stations": stations}
    return None
