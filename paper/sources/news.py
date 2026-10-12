"""Headlines from RSS feeds and Hacker News, grouped into sections."""

import html
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import feedparser
import requests

UA = {"User-Agent": "Mozilla/5.0 (newspaper bot; personal use)"}
TAG = re.compile(r"<[^>]+>")
IMG = re.compile(r"""<img[^>]+src=["']([^"']+)["']""", re.I)


def _clean(text):
    return re.sub(r"\s+", " ", html.unescape(TAG.sub(" ", text or ""))).strip()


def _source_name(feed, url):
    title = (feed.feed.get("title") or "").strip()
    host = urlparse(url).netloc.removeprefix("www.")
    # Some feeds are just called "News" or "Local News"; the site name says more.
    return title if title and title.lower() not in {"news", "local news", "home"} else host


def _feed_items(url, since):
    resp = requests.get(url, headers=UA, timeout=20)
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)
    source = _source_name(feed, url)
    items = []
    for e in feed.entries:
        when = e.get("published_parsed") or e.get("updated_parsed")
        if when and datetime(*when[:6], tzinfo=timezone.utc) < since:
            continue
        body = e.get("content", [{}])[0].get("value", "") if e.get("content") else ""
        image = IMG.search(body) or IMG.search(e.get("summary", ""))
        media = (e.get("media_content") or e.get("media_thumbnail") or [{}])[0].get("url")
        items.append({
            "title": _clean(e.get("title")),
            "source": source,
            "url": e.get("link"),
            "summary": re.sub(r"\s*\[(…|\.\.\.)\]\s*$", "", _clean(e.get("summary") or body))[:900],
            "image": image.group(1) if image else media,
            "score": None,
        })
    return items


def _hacker_news(limit=20):
    ids = requests.get(
        "https://hacker-news.firebaseio.com/v0/topstories.json", timeout=20
    ).json()[:limit]
    items = []
    for story_id in ids:
        it = requests.get(
            f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json", timeout=20
        ).json() or {}
        if it.get("type") != "story" or not it.get("url"):
            continue
        items.append({
            "title": _clean(it.get("title")),
            "source": "Hacker News",
            "url": it["url"],
            "summary": "",
            "image": None,
            "score": it.get("score", 0),
        })
    items.sort(key=lambda s: s["score"], reverse=True)
    return items


def _section(feeds, since):
    items = []
    for url in feeds:
        try:
            items.extend(_feed_items(url, since))
        except requests.RequestException as e:
            print(f"news: skipping {url}: {e}")
    return items


def fetch(cfg):
    """{"tech": [...], "local": [...], "world": [...]} candidate stories for the writer."""
    n = cfg["news"]
    since = datetime.now(timezone.utc) - timedelta(hours=36)
    sections = {
        "tech": _section(n.get("tech_feeds", []), since),
        "local": _section(n.get("local_feeds", []), since),
        "world": _section(n.get("world_feeds", []), since),
    }
    if n.get("hacker_news", True):
        try:
            sections["tech"].extend(_hacker_news()[:10])
        except requests.RequestException as e:
            print(f"news: skipping Hacker News: {e}")
    return sections
