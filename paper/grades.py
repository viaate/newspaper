"""Flag grades under the threshold and track day-over-day changes."""

import hashlib
import json
import re


def annotate(courses, threshold, data_dir, today, save=True):
    """Add `change` (vs. the last saved day) and `below`, flagged classes first."""
    path = data_dir / "grade_history.json"
    history = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    earlier = [d for d in history if d < today.isoformat()]
    previous = history[max(earlier)] if earlier else {}

    shown = []
    for c in courses:
        grade = c.get("grade")
        if grade is None and not (c.get("missing") or c.get("upcoming")):
            continue  # advisory, clubs and other ungraded sections
        before = c.get("previous", previous.get(c["course"]))
        c["change"] = round(grade - before, 2) if grade is not None and before is not None else None
        c["below"] = grade is not None and grade < threshold
        shown.append(c)

    shown.sort(key=lambda c: (not c["below"], c["grade"] if c["below"] else 0, c["course"]))

    if save:
        history[today.isoformat()] = {c["course"]: c["grade"] for c in shown if c["grade"] is not None}
        keep = sorted(history)[-60:]
        data_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({d: history[d] for d in keep}, indent=1), encoding="utf-8")
    return shown


# Percent cutoffs on a 4.0 scale, with x.5 rounding up (92.5 is an A).
SCALE = [
    (92.5, "A", 4.0), (89.5, "A-", 3.7), (86.5, "B+", 3.3), (82.5, "B", 3.0), (79.5, "B-", 2.7),
    (76.5, "C+", 2.3), (72.5, "C", 2.0), (69.5, "C-", 1.7), (66.5, "D+", 1.3), (62.5, "D", 1.0),
    (59.5, "D-", 0.7), (0, "F", 0.0),
]


def letter(percent):
    """(letter, points) for a percent grade."""
    return next((l, p) for cut, l, p in SCALE if percent >= cut)


def gpa(courses, cfg):
    """Unweighted and weighted GPA from current grades. Weighted adds `bonus` percentage
    points to classes whose names match `weighted` (Accelerated, AP...) before converting."""
    g = cfg.get("gpa", {})
    bonus = g.get("weighted_bonus", 5)
    weighted = re.compile(g.get("weighted", r"\bAccelerated\b|\bAP\b|\bHonors\b"))
    graded = [c for c in courses if c.get("grade") is not None]
    for c in graded:
        c["letter"], points = letter(c["grade"])
        c["weighted"] = bool(weighted.search(c["course"]))
        c["points"], c["weighted_points"] = points, letter(c["grade"] + (bonus if c["weighted"] else 0))[1]
    if not graded:
        return None
    return {
        "unweighted": sum(c["points"] for c in graded) / len(graded),
        "weighted": sum(c["weighted_points"] for c in graded) / len(graded),
        "classes": len(graded),
        "bonus": bonus,
    }


# Comments that say nothing about the work itself.
ROUTINE = re.compile(r"^(completion( grade)?|in[- ]class feedback|name|(\w+ )?grid completed.*|completed?|checked)\W*$", re.IGNORECASE)


def fresh_comments(courses, data_dir, today, save=True, limit=4):
    """Teacher comments seen for the first time today, newest first. The first run only
    looks back a week, so the paper doesn't open with a month of old notes."""
    path = data_dir / "comments_seen.json"
    first_run = not path.exists()
    seen = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    new = []
    for c in courses:
        for n in c.get("comments", []):
            key = f"{n['id']}:{hashlib.sha1(n['comment'].encode()).hexdigest()[:10]}"
            first_seen = seen.setdefault(key, today.isoformat())
            recent = (today - n["graded"]).days <= (7 if first_run else 14)
            if first_seen == today.isoformat() and recent and not ROUTINE.match(n["comment"]):
                new.append({"course": c["course"], **n})
    if save:
        data_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(seen, indent=1), encoding="utf-8")
    return sorted(new, key=lambda n: n["graded"], reverse=True)[:limit]
