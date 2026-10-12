"""Yesterday's NFL result for one team, from ESPN's public schedule feed."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

SCHEDULE = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{team}/schedule"


def _score(competitor):
    score = competitor.get("score")
    return score.get("displayValue") if isinstance(score, dict) else score


def last_night(cfg, today):
    """The team's game if it finished yesterday (local time), else None."""
    team = cfg.get("sports", {}).get("nfl_team", "")
    if not team:
        return None
    tz = ZoneInfo(cfg["paper"]["timezone"])
    yesterday = today - timedelta(days=1)
    for season_type in (2, 3):  # regular season, then playoffs
        r = requests.get(SCHEDULE.format(team=team), params={"seasontype": season_type}, timeout=20)
        r.raise_for_status()
        data = r.json()
        for event in data.get("events", []):
            game = event["competitions"][0]
            if not game["status"]["type"].get("completed"):
                continue
            played = datetime.fromisoformat(event["date"].replace("Z", "+00:00")).astimezone(tz).date()
            if played != yesterday:
                continue
            us = next(c for c in game["competitors"] if c["team"]["abbreviation"].lower() == team.lower())
            them = next(c for c in game["competitors"] if c is not us)
            return {
                "team": us["team"]["nickname"],
                "opponent": them["team"]["nickname"],
                "score": _score(us),
                "opponent_score": _score(them),
                "result": "W" if us.get("winner") else "L" if them.get("winner") else "T",
                "home": us.get("homeAway") == "home",
                "week": (event.get("week") or {}).get("text", ""),
                "record": data.get("team", {}).get("recordSummary", ""),
                "standing": data.get("team", {}).get("standingSummary", ""),
                "weekday": played.strftime("%A"),
            }
    return None
