"""`python -m paper check`: test every key and connection, without printing any secrets."""

import imaplib
import shutil
import subprocess
from datetime import date

import anthropic
import requests

from . import comic, writer
from .sources import calendars, gmail, lunch, schoology, sports, weather

OK, BAD, SKIP = "✓", "✗", "–"


def _line(mark, name, detail):
    print(f"  {mark} {name:<14} {detail}")


def _try(name, fn, missing=None):
    """Run one check. A check returns its detail, or (mark, detail) for "not set up yet"."""
    if missing:
        _line(SKIP, name, missing)
        return
    try:
        result = fn()
        mark, detail = result if isinstance(result, tuple) else (OK, result)
        _line(mark, name, detail)
    except Exception as e:  # report and keep checking the rest
        _line(BAD, name, f"{type(e).__name__}: {str(e)[:110]}")


def run(cfg):
    s = cfg["secrets"]
    today = date.today()
    print("The Olivia Times: setup check\n")

    def schoology_check():
        api = schoology.Schoology(s["SCHOOLOGY_KEY"], s["SCHOOLOGY_SECRET"])
        me = api.get("/users/me")
        uid = me.get("uid") or me.get("id")
        sections = api.paged(f"/users/{uid}/sections", "section")
        return f"signed in; {len(sections)} classes"

    def claude_check():
        model = anthropic.Anthropic(api_key=s["ANTHROPIC_API_KEY"]).models.retrieve(writer.MODEL)
        return f"key works; {model.display_name} available"

    def gemini_check():
        return f"key works; comics will use {comic._model(cfg, s['GEMINI_API_KEY'])}"

    def gmail_check():
        imap = imaplib.IMAP4_SSL("imap.gmail.com")
        imap.login(s["GMAIL_ADDRESS"], s["GMAIL_APP_PASSWORD"].replace(" ", ""))
        found = gmail.latest_digest(imap, cfg["email"]["digest_subject"])
        imap.logout()
        return f"signed in; {'school digest found' if found else 'no school digest in the last 2 days yet'}"

    def calendar_check():
        events = calendars.fetch(cfg, today)
        return f"{len(events)} events in the next 7 days"

    def lunch_check():
        menu = lunch.fetch(cfg, today)
        if menu is None:
            return "page read; no menu posted for today"
        return "page read; no school today" if menu["no_school"] else f"page read; {len(menu['stations'])} stations today"

    def chiefs_check():
        game = sports.last_night(cfg, today)
        return f"feed works; {game['team']} {game['score']}-{game['opponent_score']} last night" if game else "feed works; no game last night"

    def chromium_check():
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            version = browser.version
            browser.close()
        return f"starts (version {version})"

    def printer_check():
        if not shutil.which("lpstat"):
            raise RuntimeError("CUPS isn't installed (no lpstat)")
        printers = subprocess.run(["lpstat", "-e"], capture_output=True, text=True).stdout.split()
        default = subprocess.run(["lpstat", "-d"], capture_output=True, text=True).stdout.strip()
        wanted = cfg["printer"].get("name", "")
        if wanted and wanted not in printers:
            raise RuntimeError(f"no printer named {wanted!r}; found: {', '.join(printers) or 'none'}")
        if not printers:
            return SKIP, "no printer set up yet (see README, step 4)"
        return f"using {wanted or default.split(':')[-1].strip() or printers[0]} (found: {', '.join(printers)})"

    def timers_check():
        out = subprocess.run(
            ["systemctl", "--user", "list-timers", "olivia-times-*", "--no-pager", "--no-legend"],
            capture_output=True, text=True,
        ).stdout.strip().splitlines()
        if not out:
            return SKIP, "not scheduled yet: bash scripts/install.sh"
        return "next: " + " | ".join(" ".join(line.split()[:4]) for line in out)

    need = lambda *keys: None if all(s.get(k) for k in keys) else f"add {' and '.join(keys)} to .env"
    _try("Schoology", schoology_check, need("SCHOOLOGY_KEY", "SCHOOLOGY_SECRET"))
    _try("Claude", claude_check, need("ANTHROPIC_API_KEY"))
    _try("Gemini", gemini_check, need("GEMINI_API_KEY"))
    _try("Gmail", gmail_check, need("GMAIL_ADDRESS", "GMAIL_APP_PASSWORD"))
    _try("Calendar", calendar_check, need("CALENDAR_URLS"))
    _try("Weather", lambda: "{summary}, high {high}°".format(**weather.fetch(cfg)["today"]))
    _try("Lunch", lunch_check)
    _try("Chiefs", chiefs_check)
    avatar = comic.avatar_path(cfg)
    _line(OK if avatar.exists() else SKIP, "Avatar",
          "set" if avatar.exists() else "not yet: python -m paper avatar make data/photos/*")
    _try("Chromium", chromium_check)
    _try("Printer", printer_check)
    _try("Schedule", timers_check)
    print(f"\n  {OK} works   {BAD} needs fixing   {SKIP} not set up yet (that part is left out)")
