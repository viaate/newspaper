"""Grades and assignments from Schoology's REST API (v1, two-legged OAuth 1.0a).

The key and secret come from https://<school>.schoology.com/api while signed in.
They act as you, so they can only see your own classes and grades.
"""

import re
from datetime import date, datetime, timedelta

import requests
from requests_oauthlib import OAuth1

API = "https://api.schoology.com/v1"

# Values of an assignment grade's "exception" field (1 is Excused, 4 is Late).
EXCEPTIONS = {2: "Incomplete", 3: "Missing"}
# Grading categories whose grades count as tests and other big grades.
MAJOR = r"exam|test|midterm|final|assessment|essay|project|portfolio"


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
    # Unrounded: a 92.46 must stay under a 92.5 threshold.
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _due(value):
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _assignment(api, sid, aid):
    try:
        return api.get(f"/sections/{sid}/assignments/{aid}")
    except requests.RequestException:
        return {}


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
    recent_since = today - timedelta(days=cfg["grades"].get("recent_days", 7))
    major = re.compile(cfg["grades"].get("major", MAJOR), re.IGNORECASE)
    api = Schoology(s["SCHOOLOGY_KEY"], s["SCHOOLOGY_SECRET"])

    me = api.get("/users/me")
    uid = me["uid"] if "uid" in me else me["id"]
    sections = {str(x["id"]): x for x in api.paged(f"/users/{uid}/sections", "section")}

    # The calendar holds every class's due work, including what a linked class's
    # assignment list leaves out (English 10's comes back empty) and discussions.
    calendar = {}
    for e in api.paged(f"/users/{uid}/events", "event",
                       start_date=today.isoformat(), end_date=week_end.isoformat()):
        calendar.setdefault(str(e.get("section_id") or e.get("realm_id")), []).append(e)

    courses, week, agenda = [], [], []
    for sid, section in sections.items():
        name = section.get("course_title") or section.get("section_title") or "Class"
        assignments = {
            str(a["id"]): a for a in api.paged(f"/sections/{sid}/assignments", "assignment")
        }
        # Asked one class at a time: the all-classes /grades list files a linked class
        # under its linked section's ID, which doesn't match the ID in the class list.
        grades = next(iter(api.get(f"/users/{uid}/grades", section_id=sid).get("section") or []), {})
        categories = {c.get("id"): c for c in grades.get("grading_category") or []}
        scored = {}
        for period in grades.get("period") or []:
            for g in period.get("assignment") or []:
                if g.get("grade") not in (None, "") or g.get("exception"):
                    scored[str(g.get("assignment_id"))] = g

        def lookup(aid):
            # A linked class's list can leave graded work out; fetch that one directly.
            return assignments.get(aid) or _assignment(api, sid, aid)

        missing, recent = [], []
        for aid, g in scored.items():
            exception = int(g.get("exception") or 0)
            score = _number(g.get("grade"))
            max_points = _number(g.get("max_points") or assignments.get(aid, {}).get("max_points")) or 0
            graded = datetime.fromtimestamp(int(g.get("timestamp") or 0)).date()
            kind = None
            if exception in EXCEPTIONS:  # marked Missing or Incomplete: always worth chasing
                kind = EXCEPTIONS[exception]
            elif score == 0 and max_points > 0:
                kind = "Zero"
            if kind:
                a = lookup(aid)
                due = _due(a.get("due"))
                # A plain zero is just a grade after a while; stop listing it.
                if kind == "Zero" and (today - (due or graded)).days > cfg["grades"].get("zero_days", 30):
                    continue
                missing.append({"title": a.get("title") or "Untitled assignment", "kind": kind, "due": due})

            # Recently graded tests, exams, essays and projects, good or bad.
            category = categories.get(g.get("category_id"), {})
            if score is not None and max_points > 0 and graded >= recent_since and major.search(category.get("title") or ""):
                recent.append({
                    "title": lookup(aid).get("title") or "Untitled assignment",
                    "category": category.get("title"),
                    "weight": _number(category.get("weight")),
                    "score": score, "max": max_points, "percent": score / max_points * 100,
                    "graded": graded,
                })

        upcoming = []
        for aid, a in assignments.items():
            due = _due(a.get("due"))
            if due and today <= due <= week_end and aid not in scored:
                upcoming.append({"title": a.get("title") or "Assignment", "due": due})
        listed = {u["title"].casefold() for u in upcoming}
        for e in calendar.get(sid, []):
            title, due = e.get("title") or "Assignment", _due(e.get("start"))
            if not (due and today <= due <= week_end):
                continue
            if e.get("type") == "event":  # class agenda, not something to hand in
                agenda.append({"course": name, "title": title, "day": due})
            elif str(e.get("assignment_id")) not in scored and title.casefold() not in listed:
                upcoming.append({"title": title, "due": due})
                listed.add(title.casefold())
        week.extend({"course": name, **u} for u in upcoming)

        courses.append({
            "course": name,
            "grade": _current_grade(grades) if grades else None,
            "missing": sorted(missing, key=lambda m: m["due"] or date.min),
            "upcoming": sorted(upcoming, key=lambda u: u["due"]),
            "recent": sorted(recent, key=lambda r: r["graded"], reverse=True),
        })

    week.sort(key=lambda w: (w["due"], w["course"]))
    agenda.sort(key=lambda a: (a["day"], a["course"]))
    return {"courses": courses, "week": week, "agenda": agenda}
