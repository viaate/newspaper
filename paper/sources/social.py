"""Public TikTok and Instagram numbers, and an estimate of what TikTok paid.

No logins. TikTok's profile page has exact followers and likes, and yt-dlp lists the
videos with their view counts (TikTok rounds those, like 2.8M). Instagram's public page
shows followers (rounded, like 63K) and the number of posts; views need a login, so
they're left out. Each run's numbers are saved to data/social.json so the paper can say
what changed since the last paper.
"""

import json
import re
from datetime import datetime

import requests

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36"
REHYDRATION = re.compile(r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>', re.DOTALL)


def _count(text):
    """'63K' -> 63000, '1.2M' -> 1200000, '12,345' -> 12345."""
    m = re.fullmatch(r"([\d.,]+)\s*([KMB]?)", text.strip(), re.IGNORECASE)
    if not m:
        return None
    return round(float(m.group(1).replace(",", "")) * {"": 1, "K": 1e3, "M": 1e6, "B": 1e9}[m.group(2).upper()])


def tiktok(user):
    page = requests.get(f"https://www.tiktok.com/@{user}", headers={"User-Agent": UA, "Accept-Language": "en-US"}, timeout=30)
    page.raise_for_status()
    info = json.loads(REHYDRATION.search(page.text).group(1))["__DEFAULT_SCOPE__"]["webapp.user-detail"]["userInfo"]
    stats = info.get("statsV2") or info["stats"]

    import yt_dlp  # only needed here, and slow to import
    with yt_dlp.YoutubeDL({"extract_flat": True, "quiet": True, "no_warnings": True}) as ydl:
        listing = ydl.extract_info(f"https://www.tiktok.com/@{user}", download=False)
    videos = {str(e["id"]): e.get("view_count") or 0 for e in listing.get("entries") or []}
    return {"followers": int(stats["followerCount"]), "likes": int(stats["heartCount"]),
            "videos": int(stats["videoCount"]), "views": sum(videos.values()), "by_video": videos}


def instagram(user):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(user_agent=UA, locale="en-US")
        page.goto(f"https://www.instagram.com/{user}/", wait_until="domcontentloaded", timeout=60000)
        meta = page.locator('meta[property="og:description"]')
        meta.first.wait_for(state="attached", timeout=20000)
        text = meta.first.get_attribute("content") or ""
        browser.close()
    m = re.search(r"([\d.,]+[KMB]?) Followers, .*?([\d.,]+[KMB]?) Posts", text, re.IGNORECASE)
    if not m:
        raise RuntimeError("Instagram's public page didn't show follower counts")
    return {"followers_text": m.group(1), "followers": _count(m.group(1)), "posts": _count(m.group(2))}


def fetch(cfg, now=None):
    """Today's numbers, what changed since the last saved run, and TikTok's estimated pay."""
    now = now or datetime.now().astimezone()
    s = cfg.get("social", {})
    path = cfg["data_dir"] / "social.json"
    history = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    out = {"errors": []}
    snap = {"when": now.isoformat()}
    for name, fn in (("tiktok", tiktok), ("instagram", instagram)):
        if not s.get(name):
            continue
        try:
            snap[name] = fn(s[name])
        except Exception as e:  # one platform down shouldn't drop the other
            out["errors"].append(f"{name}: {type(e).__name__}")
            print(f"social: {name}: {e}")

    # Compare with the last run from an earlier day.
    earlier = [h for h in history if h["when"][:10] < now.date().isoformat()]
    before = earlier[-1] if earlier else None
    hours = (now - datetime.fromisoformat(before["when"])).total_seconds() / 3600 if before else None

    tt, ig = snap.get("tiktok"), snap.get("instagram")
    if tt:
        out["tiktok"] = {k: tt[k] for k in ("followers", "likes", "videos", "views")} | {"user": s["tiktok"]}
        old = (before or {}).get("tiktok")
        if old:
            gained = sum(max(0, v - old["by_video"].get(vid, 0)) for vid, v in tt["by_video"].items())
            qualified = gained * s.get("tiktok_qualified", 0.35)
            out["tiktok"] |= {
                "followers_change": tt["followers"] - old["followers"], "views_change": gained,
                "hours": round(hours), "earned": qualified / 1000 * s.get("tiktok_rpm", 0.26),
            }
    if ig:
        out["instagram"] = ig | {"user": s["instagram"]}
        old = (before or {}).get("instagram")
        if old and old.get("followers") and ig["followers"]:
            out["instagram"]["followers_change"] = ig["followers"] - old["followers"]
    if tt or ig:
        out["followers"] = (tt or {}).get("followers", 0) + ((ig or {}).get("followers") or 0)
        history = [h for h in history if h["when"][:10] != now.date().isoformat()] + [snap]
        path.write_text(json.dumps(history[-120:], indent=1), encoding="utf-8")
    return out
