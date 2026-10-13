"""Build and print the morning paper.

    python -m paper build              # make out/YYYY-MM-DD.pdf (and out/latest.pdf)
    python -m paper build --sample     # sample grades and email, live weather and news
    python -m paper print              # print this morning's paper (building it first if needed)
    python -m paper run                # build, then print
    python -m paper avatar make PHOTOS # draw avatar options A-D for the comic
    python -m paper avatar pick B      # keep option B
    python -m paper check              # test every key and connection
"""

import argparse
import json
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

from . import comic, config, grades, headlines, images, printer, puzzles, render, seen, spend, writer
from . import week as weekly
from .dates import fmt
from .sources import ai_usage, calendars, codex, gmail, lunch, news, overnight, schoology, social, sports, weather

SAMPLE = Path(__file__).resolve().parent / "sample.json"


def _load_sample(today):
    s = json.loads(SAMPLE.read_text(encoding="utf-8"))

    def on(days):
        return today + timedelta(days=days) if days is not None else None

    courses, week = [], []
    for c in s["courses"]:
        upcoming = [{"title": u["title"], "due": on(u["due_in_days"])} for u in c.get("upcoming", [])]
        courses.append({
            "course": c["course"], "grade": c["grade"], "previous": c.get("previous"),
            "missing": [{"title": m["title"], "kind": m["kind"], "due": on(m.get("due_in_days"))}
                        for m in c.get("missing", [])],
            "upcoming": upcoming,
        })
        week += [{"course": c["course"], **u} for u in upcoming]
    week.sort(key=lambda w: (w["due"], w["course"]))
    return courses, week, s["emails"], s.get("edition")


def _week_by_day(week, today):
    days = {}
    for w in week:
        days.setdefault(w["due"], []).append(w)
    out = []
    for d in sorted(days):
        label = "Today" if d == today else "Tomorrow" if d == today + timedelta(days=1) else fmt(d, "%a %b %-d")
        out.append({"label": label, "items": days[d]})
    return out


def _snow_watch(forecast):
    if not forecast:
        return []
    ahead = forecast["days"][1:4]
    snowy = [d for d in ahead if d["snow"] > 0 or "snow" in d["summary"].lower()]
    if snowy:
        return [f"Snow forecast {d['date'].strftime('%A')}" + (f": {d['snow']} in." if d["snow"] else ".")
                for d in snowy]
    return [f"No snow in the forecast through {ahead[-1]['date'].strftime('%A')}."]


def _build_due(cfg, day):
    """When the day's build is scheduled: 15 minutes before its print time."""
    h, m = (int(x) for x in cfg["schedule"]["weekend" if day.weekday() >= 5 else "weekday"].split(":"))
    return datetime.combine(day, datetime.min.time()).replace(hour=h, minute=m) - timedelta(minutes=15)


def catchup_needed(cfg, day, now):
    """True when today's build time has passed and there's still no paper (the computer was off)."""
    return now >= _build_due(cfg, day) and not (cfg["out_dir"] / f"{day}.pdf").exists()


def _print_time(cfg, day):
    """Today's print time from [schedule], like "6:50 A.M."."""
    hhmm = cfg["schedule"]["weekend" if day.weekday() >= 5 else "weekday"]
    h, m = (int(x) for x in hhmm.split(":"))
    return f"{(h - 1) % 12 + 1}:{m:02d} {'A.M.' if h < 12 else 'P.M.'}"


def _countdowns(cfg, today, limit=3):
    ahead = []
    for c in cfg.get("countdown", []):
        when = date.fromisoformat(str(c["date"]))
        if when >= today:
            ahead.append({"name": c["name"], "days": (when - today).days, "date": when})
    return sorted(ahead, key=lambda c: c["days"])[:limit]


def _photos(cfg, today, stories, news_items):
    """Newsprint photos for the lead story and the first side story, keyed by URL."""
    feed_image = {n["url"]: n.get("image") for n in news_items}
    found = {}
    for s in stories[:2]:
        source = feed_image.get(s["url"]) or images.find_image(s["url"])
        if source:
            path = images.newsprint(source, cfg["out_dir"] / f"{today}-photo-{len(found) + 1}.png")
            if path:
                found[s["url"]] = Path(path).as_uri()
    return found


def _feature_photo(cfg, today, feature, stories):
    """A newsprint photo for the front page's Feature, when its story has one."""
    if not feature or not feature.get("url"):
        return None
    item = next((n for section in stories.values() for n in section if n["url"] == feature["url"]), {})
    source = item.get("image") or images.find_image(feature["url"])
    path = images.newsprint(source, cfg["out_dir"] / f"{today}-photo-feature.png") if source else None
    return Path(path).as_uri() if path else None


def _volume_and_number(cfg, today):
    """A new volume every January 1, and issue numbers that start over with it."""
    first = date.fromisoformat(cfg["paper"].get("first_issue", today.isoformat()))
    start = max(first, date(today.year, 1, 1))
    return today.year - first.year + 1, (today - start).days + 1


def _money(gumroad, socials, now):
    day_ago, month_ago = now - timedelta(days=1), now - timedelta(days=30)
    return {
        "tiktok": (socials.get("tiktok") or {}).get("earned"),
        "tiktok_hours": (socials.get("tiktok") or {}).get("hours"),
        "gumroad_day": sum(g["amount"] for g in gumroad if g["when"] >= day_ago),
        "gumroad_day_count": sum(1 for g in gumroad if g["when"] >= day_ago),
        "gumroad_month": sum(g["amount"] for g in gumroad if g["when"] >= month_ago),
        "gumroad_month_count": sum(1 for g in gumroad if g["when"] >= month_ago),
    }


def build(cfg, sample=False, today=None, png=False):
    today = today or date.today()
    cfg["out_dir"].mkdir(parents=True, exist_ok=True)
    notes = []
    ledger_start = spend.mark(cfg)  # this issue's API costs are what's added after here

    # One bad source shouldn't stop the paper, so each is fetched on its own.
    forecast, stories = None, {"tech": [], "local": [], "world": [], "interest": []}
    printed = seen.load(cfg, today)
    try:
        forecast = weather.fetch(cfg)
    except Exception as e:
        notes.append("Weather was unavailable this morning.")
        print(f"weather: {e}")
    try:
        stories = seen.unseen(news.fetch(cfg), printed, today)
    except Exception as e:
        notes.append("News was unavailable this morning.")
        print(f"news: {e}")

    menu = chiefs = None
    try:
        menu = lunch.fetch(cfg, today)
    except Exception as e:
        print(f"lunch: {e}")
    try:
        chiefs = sports.last_night(cfg, today)
    except Exception as e:
        print(f"sports: {e}")

    sample_copy, packages, events, limits, slept, gumroad, socials, codex_limits = None, [], [], [], [], [], {}, None
    if sample:
        courses, week, mail, sample_copy = _load_sample(today)
        chiefs = chiefs or json.loads(SAMPLE.read_text(encoding="utf-8")).get("chiefs")
        notes.append("Preview: grades, assignments, email, packages, the Chiefs score and page-3 features are sample data.")
    else:
        courses, week, mail = [], [], []
        if cfg["secrets"]["SCHOOLOGY_KEY"]:
            try:
                s = schoology.fetch(cfg, today)
                courses, week = s["courses"], s["week"]
            except Exception as e:
                notes.append("Couldn't reach Schoology this morning.")
                print(f"schoology: {e}")
        try:
            got = gmail.fetch(cfg)
            mail, packages, gumroad = got["emails"], got["packages"], got["gumroad"]
        except Exception as e:
            notes.append("Couldn't read email this morning.")
            print(f"gmail: {e}")
        try:
            events = calendars.fetch(cfg, today)
        except Exception as e:
            notes.append("Couldn't read the calendar this morning.")
            print(f"calendar: {e}")
        try:
            limits = ai_usage.claude_limits(cfg)
        except Exception as e:
            print(f"claude limits: {e}")
        try:
            codex_limits = codex.limits(cfg)
        except Exception as e:
            print(f"codex limits: {e}")
        try:
            slept = overnight.sessions(cfg)
        except Exception as e:
            print(f"overnight: {e}")
        try:
            socials = social.fetch(cfg)
        except Exception as e:
            print(f"social: {e}")

    threshold = cfg["grades"]["threshold"]
    courses = grades.annotate(courses, threshold, cfg["data_dir"], today, save=not sample)
    gpa = grades.gpa(courses, cfg)
    notes_from_teachers = grades.fresh_comments(courses, cfg["data_dir"], today, save=not sample)
    if not sample:
        weekly.log_overnight(cfg, today, slept)
    # Sundays look back over the week.
    week_review = weekly.review(cfg, today, courses, gumroad) if today.weekday() == 6 and not sample else None
    style = comic.style_for(today, cfg["comic"]["styles"])
    print_time = _print_time(cfg, today)
    ctx = {
        "today": today, "threshold": threshold, "courses": courses, "week": week,
        "emails": mail, "packages": packages, "calendar": events, "weather": forecast, "news": stories,
        "lunch": menu, "chiefs": chiefs, "overnight": slept, "gumroad": gumroad, "socials": socials,
        "teacher_notes": notes_from_teachers, "week_review": week_review,
        "past_titles": headlines.load(cfg, today),
        "past_stories": [r["headline"] for r in printed if (today - date.fromisoformat(r["date"])).days <= 10],
        # No lunch menu (no school, or a weekend) and no Sunday review leaves the front page's lower half free.
        "front_page_has_room": not (menu and not menu.get("no_school")) and not week_review,
    }

    edition = writer.write(cfg, ctx, style, print_time)
    if edition is None:
        edition = writer.fallback(cfg, ctx, style, sample_copy)
    if not sample:
        headlines.save(cfg, today, edition)
        seen.save(cfg, today, edition, stories)
    # What was written, kept beside the PDF (handy for fixing a layout without rewriting it).
    (cfg["out_dir"] / f"{today}{'-sample' if sample else ''}.json").write_text(json.dumps(edition, indent=1, default=str), encoding="utf-8")

    # Page 3: today's puzzles, and the answers to yesterday's.
    seed = today.toordinal()
    crossword = puzzles.crossword([(c["answer"], c["clue"]) for c in edition["crossword"]], seed)
    words = puzzles.real_words(edition.get("jumble") or [], json.dumps({k: v for k, v in edition.items() if k != "jumble"}, default=str),
                               [c["answer"] for c in edition.get("crossword") or []])
    scrambles = puzzles.jumble(words, seed)
    answers = puzzles.yesterdays_answers(cfg["data_dir"], today)
    sat = None
    if edition.get("sat_question") and edition.get("sat_answer"):
        letter = edition["sat_answer"].strip()[:1].upper()
        choices = edition.get("sat_choices") or []
        pick = "ABCD".find(letter)
        sat = {"answer": letter, "choice": choices[pick] if 0 <= pick < len(choices) else "", "why": edition.get("sat_why", "")}
    if not sample:
        puzzles.save_answers(cfg["data_dir"], today, crossword, scrambles, sat)

    strip = None
    if edition.get("comic"):
        drawn = comic.draw(cfg, edition["comic"], style, cfg["out_dir"] / f"{today}-comic.png")
        strip = Path(drawn).as_uri() if drawn else None

    p = cfg["paper"]
    volume, number = _volume_and_number(cfg, today)
    pages = 4
    api = spend.since(cfg, ledger_start)
    paper_cost = pages * cfg.get("price", {}).get("paper_per_100_sheets", 2.40) / 100
    price = {"total": paper_cost + sum(api.values()), "paper": paper_cost,
             "writing": api["anthropic"], "comic": api["gemini"]}
    out_pdf = cfg["out_dir"] / f"{today}{'-sample' if sample else ''}.pdf"
    render.render({
        "paper": p,
        "print_time": print_time,
        "countdowns": _countdowns(cfg, today),
        "lunch": menu,
        "campus": cfg.get("lunch", {}).get("campus", "").replace("-", " ").title(),
        "chiefs": chiefs,
        "issue": number,
        "volume": volume,
        "price": price,
        "socials": socials,
        "money": _money(gumroad, socials, datetime.now().astimezone()),
        "cfg_social": cfg.get("social", {}),
        "today": today,
        "edition": edition,
        "weather": forecast,
        "snow": _snow_watch(forecast),
        "courses": courses,
        "threshold": threshold,
        "week": _week_by_day(week, today),
        "photos": _photos(cfg, today, edition["tech"], stories["tech"]),
        "feature_photo": _feature_photo(cfg, today, edition.get("feature"), stories),
        "style": style,
        "strip": strip,
        "has_avatar": comic.avatar_path(cfg).exists(),
        "crossword": crossword,
        "scrambles": scrambles,
        "answers": answers,
        "notes": notes,
        "gpa": gpa,
        "tests": sorted(({"course": c["course"], **r} for c in courses for r in c.get("recent", [])),
                        key=lambda r: r["graded"], reverse=True),
        "missing": [{"course": c["course"], **m} for c in courses for m in c["missing"]],
        "limits": limits,
        "codex": codex_limits,
        "teacher_notes": notes_from_teachers,
        "week_review": week_review,
        "overnight": [{**o, "note": note} for o, note in zip(slept, edition.get("overnight", []) + [""] * len(slept))],
        "spend": spend.summary(cfg, today),
    }, out_pdf, png=png)
    if not sample:
        shutil.copyfile(out_pdf, cfg["out_dir"] / "latest.pdf")
    print(f"built {out_pdf}")
    return out_pdf


def _update_archive(cfg):
    """Add the new issue to the archive site, and publish it if set up. Never stops the paper."""
    a = cfg.get("archive", {})
    if not a.get("passcode"):
        return
    try:
        from . import archive
        archive.build(cfg)
        if a.get("publish") and a.get("repo"):
            print(f"archive: published to {archive.publish(cfg)}")
    except Exception as e:
        print(f"archive: {type(e).__name__}: {e}")


def main():
    ap = argparse.ArgumentParser(description="The morning paper.")
    ap.add_argument("command", choices=["build", "print", "run", "avatar", "check", "archive", "catchup"])
    ap.add_argument("args", nargs="*", help="for avatar: make PHOTO... | pick LETTER; for archive: publish")
    ap.add_argument("--sample", action="store_true", help="use sample grades, email and features")
    ap.add_argument("--png", action="store_true", help="also save PNGs of the pages")
    ap.add_argument("--date", type=date.fromisoformat, help="pretend it's this date (YYYY-MM-DD)")
    ap.add_argument("--config", help="path to config.toml")
    args = ap.parse_args()
    cfg = config.load(args.config)

    if args.command == "check":
        from . import check
        check.run(cfg)
        return

    if args.command == "avatar":
        if args.args[:1] == ["make"] and len(args.args) > 1:
            comic.make_avatars(cfg, comic.photo_paths(args.args[1:]))
            print("Look at data/avatar/option-A..D.png, then run: python -m paper avatar pick <letter>")
        elif args.args[:1] == ["pick"] and len(args.args) == 2:
            comic.pick_avatar(cfg, args.args[1])
        else:
            ap.error("use: avatar make PHOTO... | avatar pick LETTER")
        return

    if args.command == "archive":
        from . import archive
        print(f"archive: {archive.build(cfg)} new or changed issues in site/")
        if args.args[:1] == ["publish"]:
            print(f"archive: published to {archive.publish(cfg)}")
        return

    today = args.date or date.today()
    if args.command == "catchup":
        # After the computer was off at build time: make the day's paper for the archive, never print.
        if catchup_needed(cfg, today, datetime.now()):
            build(cfg, today=today)
            _update_archive(cfg)
        else:
            print("catch-up: nothing to do")
        return
    pdf = cfg["out_dir"] / f"{today}{'-sample' if args.sample else ''}.pdf"
    # `print` builds first if this morning's paper isn't there, so it never reprints yesterday's.
    if args.command in ("build", "run") or not pdf.exists():
        pdf = build(cfg, sample=args.sample, today=today, png=args.png)
        if not args.sample:
            _update_archive(cfg)
    if args.command in ("print", "run"):
        printer.send(pdf, cfg["printer"].get("name", ""))
        print(f"sent {pdf} to the printer")


if __name__ == "__main__":
    main()
