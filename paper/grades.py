"""Flag grades under the threshold and track day-over-day changes."""

import json


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
        c["change"] = round(grade - before, 1) if grade is not None and before is not None else None
        c["below"] = grade is not None and grade < threshold
        shown.append(c)

    shown.sort(key=lambda c: (not c["below"], c["grade"] if c["below"] else 0, c["course"]))

    if save:
        history[today.isoformat()] = {c["course"]: c["grade"] for c in shown if c["grade"] is not None}
        keep = sorted(history)[-60:]
        data_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({d: history[d] for d in keep}, indent=1), encoding="utf-8")
    return shown
