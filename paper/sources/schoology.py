"""Grades and assignments from Schoology's REST API (v1, two-legged OAuth 1.0a).

The key and secret come from https://<school>.schoology.com/api while signed in.
They act as you, so they can only see your own classes and grades.
"""

from datetime import date, datetime, timedelta

import requests
from requests_oauthlib import OAuth1

API = "https://api.schoology.com/v1"

# Values of an assignment grade's "exception" field.
EXCEPTIONS = {2: "Incomplete", 3: "Missing"}


class Schoology:
    def __init__(self, key, secret):
        self.session = requests.Session()
        self.session.auth = OAuth1(key, secret)
        self.session.headers["Accept"] = "application/json"

    def get(self, path, **params):
        url = path if path.startswith("http") else f"{API}{path}"
        r = self.session.get(url, params=params, timeout=30, allow_redirects=False)
        # /users/me redirects to /users/{id}. Follow it with a freshly signed
        # request; reusing the old signature for the new URL is rejected.
        if r.is_redirect and "Location" in r.headers:
            return self.get(r.headers["Location"])
        r.raise_for_status()
        return r.json()

    def paged(self, path, key, **params):
        items, start = [], 0
        while True:
            page = self.get(path, start=start, limit=200, **params)
            batch = page.get(key) or []
            items.extend(batch)
            start += len(batch)
            if not batch or start >= int(page.get("total", start)):
                return items


def _number(value):
    try:
        return round(float(value), 1)
    except (TypeError, ValueError):
        return None


def _due(value):
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _current_grade(section):
    """The final grade for the grading period with the most recent graded work."""
    latest = {}
    for period in section.get("period") or []:
        stamps = [int(a.get("timestamp") or 0) for a in period.get("assignment") or []]
        latest[period.get("period_id")] = max(stamps, default=0)
    finals = [f for f in section.get("final_grade") or [] if f.get("grade") not in (None, "")]
    if not finals:
        return None
    best = max(finals, key=lambda f: latest.get(f.get("period_id"), 0))
    return _number(best.get("grade"))


def fetch(cfg, today=None):
    s = cfg["secrets"]
    today = today or date.today()
    week_end = today + timedelta(days=7)
    api = Schoology(s["SCHOOLOGY_KEY"], s["SCHOOLOGY_SECRET"])

    me = api.get("/users/me")
    uid = me["uid"] if "uid" in me else me["id"]
    sections = {str(x["id"]): x for x in api.paged(f"/users/{uid}/sections", "section")}
    graded = {str(x["section_id"]): x for x in api.get(f"/users/{uid}/grades").get("section") or []}

    courses, week = [], []
    for sid, section in sections.items():
        name = section.get("course_title") or section.get("section_title") or "Class"
        assignments = {
            str(a["id"]): a for a in api.paged(f"/sections/{sid}/assignments", "assignment")
        }
        grades = graded.get(sid, {})
        scored = {}
        for period in grades.get("period") or []:
            for g in period.get("assignment") or []:
                if g.get("grade") not in (None, "") or g.get("exception"):
                    scored[str(g.get("assignment_id"))] = g

        missing = []
        for aid, g in scored.items():
            a = assignments.get(aid, {})
            title = a.get("title") or "Untitled assignment"
            exception = int(g.get("exception") or 0)
            if exception in EXCEPTIONS:
                missing.append({"title": title, "kind": EXCEPTIONS[exception], "due": _due(a.get("due"))})
            elif _number(g.get("grade")) == 0 and (_number(a.get("max_points")) or 0) > 0:
                missing.append({"title": title, "kind": "Zero", "due": _due(a.get("due"))})

        upcoming = []
        for aid, a in assignments.items():
            due = _due(a.get("due"))
            if due and today <= due <= week_end and aid not in scored:
                upcoming.append({"title": a.get("title") or "Assignment", "due": due})
                week.append({"course": name, "title": a.get("title") or "Assignment", "due": due})

        courses.append({
            "course": name,
            "grade": _current_grade(grades) if grades else None,
            "missing": sorted(missing, key=lambda m: m["due"] or date.min),
            "upcoming": sorted(upcoming, key=lambda u: u["due"]),
        })

    week.sort(key=lambda w: (w["due"], w["course"]))
    return {"courses": courses, "week": week}
