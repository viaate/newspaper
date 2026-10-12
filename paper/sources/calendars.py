"""Events from calendars' private iCal links (Google Calendar, Schoology, anything with .ics).

No sign-in needed: in Google Calendar, open Settings → your calendar → "Secret address in
iCal format" and put that link in CALENDAR_URLS in .env (several links: separate with spaces).
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import icalendar
import recurring_ical_events
import requests


def fetch(cfg, today=None, days=7):
    urls = cfg["secrets"].get("CALENDAR_URLS", "").replace(",", " ").split()
    if not urls:
        return []
    tz = ZoneInfo(cfg["paper"]["timezone"])
    today = today or date.today()
    end = today + timedelta(days=days)
    events = []
    for url in urls:
        url = url.replace("webcal://", "https://", 1)
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            cal = icalendar.Calendar.from_ical(r.content)
        except (requests.RequestException, ValueError) as e:
            print(f"calendar: skipping a calendar: {e}")
            continue
        name = str(cal.get("X-WR-CALNAME", "Calendar"))
        for e in recurring_ical_events.of(cal).between(today, end):
            start = e.get("DTSTART").dt
            all_day = not isinstance(start, datetime)
            if not all_day:
                start = (start if start.tzinfo else start.replace(tzinfo=tz)).astimezone(tz)
            events.append({
                "title": str(e.get("SUMMARY", "Event")),
                "day": start if all_day else start.date(),
                "time": None if all_day else start.time(),
                "location": str(e.get("LOCATION", "") or ""),
                "calendar": name,
            })
    events.sort(key=lambda ev: (ev["day"], ev["time"] or time.min))
    return events
