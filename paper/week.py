"""Sunday's week in review: grades, TikTok, money and what Claude built over the past
seven days, from what each morning's paper saved in data/."""

import json
from datetime import date, datetime, timedelta

from . import grades as grade_math


def _load(path, empty):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else empty


def log_overnight(cfg, today, sessions):
    """Keep a short record of each night's Claude sessions for the weekly roundup."""
    path = cfg["data_dir"] / "overnight" / "log.json"
    log = _load(path, {})
    log[today.isoformat()] = [{"project": s["project"], "account": s["account"], "where": s["where"],
                               "commits": len(s.get("commits") or [])} for s in sessions]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({d: log[d] for d in sorted(log)[-60:]}, indent=1), encoding="utf-8")


def review(cfg, today, courses, gumroad):
    week_ago = today - timedelta(days=7)
    data = cfg["data_dir"]
    out = {"from": week_ago + timedelta(days=1), "to": today}

    # Grades: today's against the earliest saved day of the past week.
    history = _load(data / "grade_history.json", {})
    then_day = next((d for d in sorted(history) if week_ago.isoformat() <= d < today.isoformat()), None)
    if then_day:
        then = history[then_day]
        now = {c["course"]: c["grade"] for c in courses if c.get("grade") is not None}
        changes = sorted(((k, now[k] - then[k]) for k in now if k in then and abs(now[k] - then[k]) >= 0.01),
                         key=lambda kv: -abs(kv[1]))
        gpa = lambda g: sum(grade_math.letter(v)[1] for v in g.values()) / len(g) if g else None
        shared = {k: v for k, v in then.items() if k in now}
        out["grades"] = {"since": date.fromisoformat(then_day), "changes": changes[:4],
                         "gpa_then": gpa(shared), "gpa_now": gpa({k: now[k] for k in shared})}

    # TikTok: the newest snapshot against the oldest one from the past week.
    snaps = [s for s in _load(data / "social.json", []) if s.get("tiktok")]
    first = next((s for s in snaps if week_ago.isoformat() <= s["when"][:10] < today.isoformat()), None)
    if first and snaps[-1] is not first:
        a, b = first["tiktok"], snaps[-1]["tiktok"]
        gained = {vid: max(0, v - a["by_video"].get(vid, 0)) for vid, v in b["by_video"].items()}
        best = max(gained, key=gained.get) if gained else None
        social = cfg.get("social", {})
        views = sum(gained.values())
        out["tiktok"] = {"followers": b["followers"] - a["followers"], "views": views,
                         "earned": views * social.get("tiktok_qualified", 0.35) / 1000 * social.get("tiktok_rpm", 0.26),
                         "best": (b.get("detail", {}).get(best, {}).get("caption") or "")[:70] if best and gained[best] else "",
                         "best_views": gained.get(best, 0) if best else 0}

    # Money: Gumroad sales this week, plus TikTok's estimate.
    since = datetime.combine(week_ago + timedelta(days=1), datetime.min.time()).astimezone()
    week_sales = [g for g in gumroad if g["when"] >= since]
    out["money"] = {"gumroad": sum(g["amount"] for g in week_sales), "sales": len(week_sales),
                    "tiktok": out.get("tiktok", {}).get("earned")}

    # Claude: every night's sessions this week.
    log = _load(data / "overnight" / "log.json", {})
    nights = [s for d, day in log.items() if week_ago.isoformat() < d <= today.isoformat() for s in day]
    if nights:
        projects = []
        for s in nights:
            if s["project"] not in projects:
                projects.append(s["project"])
        out["claude"] = {"sessions": len(nights), "commits": sum(s["commits"] for s in nights), "projects": projects[:4]}
    return out
