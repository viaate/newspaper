"""Recent mail from Gmail over IMAP, using an app password.

School mail can't be read this way when the school blocks it, so a small Apps
Script in the school account (apps_script/school_digest.gs) emails a JSON
digest to the personal account each morning; it is unpacked here.
"""

import email
import html
import imaplib
import json
import re
from datetime import datetime, timedelta, timezone
from email.header import decode_header, make_header
from email.utils import parseaddr, parsedate_to_datetime
from zoneinfo import ZoneInfo

LABELS = re.compile(rb"X-GM-LABELS \(([^)]*)\)")
TAG = re.compile(r"<[^>]+>")


def _header(msg, name):
    return str(make_header(decode_header(msg.get(name, "")))).strip()


def _body(msg):
    plain, markup = None, None
    for part in msg.walk():
        if part.get_content_maintype() == "multipart" or part.get("Content-Disposition", "").startswith("attachment"):
            continue
        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        text = payload.decode(part.get_content_charset() or "utf-8", "replace")
        if part.get_content_type() == "text/plain" and plain is None:
            plain = text
        elif part.get_content_type() == "text/html" and markup is None:
            markup = html.unescape(TAG.sub(" ", text))
    return re.sub(r"\s+", " ", plain or markup or "").strip()


def _unpack_digest(body):
    try:
        items = json.loads(body)
    except ValueError:
        return None
    if not isinstance(items, list):
        return None
    return [{
        "account": "school",
        "sender": str(i.get("from", "")),
        "subject": str(i.get("subject", "")),
        "date": str(i.get("date", "")),
        "important": bool(i.get("important")),
        "body": str(i.get("body", ""))[:1200],
    } for i in items if isinstance(i, dict)]


# Shipping notices from the past week; the writer works out what arrives today.
PACKAGE_QUERY = (
    "newer_than:7d (subject:(arriving OR arrives OR delivery OR delivered OR shipped OR shipment) "
    "OR from:(amazon.com OR ups.com OR fedex.com OR usps.com OR dhl.com OR shopify.com))"
)


def _search(imap, query, limit):
    _, found = imap.search(None, "X-GM-RAW", f'"{query}"')
    for num in reversed(found[0].split()[-limit:]):  # newest first
        # BODY.PEEK leaves messages unread.
        _, parts = imap.fetch(num, "(X-GM-LABELS BODY.PEEK[])")
        meta, raw = parts[0]
        msg = email.message_from_bytes(raw)
        try:
            when = parsedate_to_datetime(msg.get("Date"))
        except (TypeError, ValueError):
            when = None
        name, addr = parseaddr(_header(msg, "From"))
        labels = LABELS.search(meta)
        yield {
            "account": "personal",
            "sender": name or addr,
            "subject": _header(msg, "Subject"),
            "when": when,
            "date": when.isoformat() if when else "",
            "important": bool(labels and b"\\Important" in labels.group(1)),
            "body": _body(msg),
        }


def fetch(cfg, limit=40):
    """{"emails": recent mail plus the school digest, "packages": shipping notices}."""
    s = cfg["secrets"]
    if not (s["GMAIL_ADDRESS"] and s["GMAIL_APP_PASSWORD"]):
        return {"emails": [], "packages": []}
    hours = cfg["email"].get("lookback_hours", 24)
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    digest_subject = cfg["email"].get("digest_subject", "")

    imap = imaplib.IMAP4_SSL("imap.gmail.com")
    try:
        imap.login(s["GMAIL_ADDRESS"], s["GMAIL_APP_PASSWORD"].replace(" ", ""))
        imap.select("INBOX", readonly=True)
        days = max(1, -(-hours // 24))

        mail, digests = [], []
        for m in _search(imap, f"newer_than:{days}d -category:promotions -category:social", limit):
            if digest_subject and m["subject"].startswith(digest_subject):
                digests.append(m)
            elif not (m["when"] and m["when"].tzinfo and m["when"] < since):
                mail.append({**m, "body": m["body"][:1200]})
        if digests:  # only the newest school digest
            newest = max(digests, key=lambda m: m["when"] or datetime.min.replace(tzinfo=timezone.utc))
            mail.extend(_unpack_digest(newest["body"]) or [])

        # Local time, so "arriving tomorrow" sent last night reads correctly.
        tz = ZoneInfo(cfg["paper"]["timezone"])
        packages = [{**m, "body": m["body"][:1200]} for m in _search(imap, PACKAGE_QUERY, 25)]
        for m in packages:
            if m["when"] and m["when"].tzinfo:
                m["when"] = m["when"].astimezone(tz)
        return {"emails": mail, "packages": packages}
    finally:
        try:
            imap.logout()
        except imaplib.IMAP4.error:
            pass
