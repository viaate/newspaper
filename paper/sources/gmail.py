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


def fetch(cfg, limit=40):
    s = cfg["secrets"]
    if not (s["GMAIL_ADDRESS"] and s["GMAIL_APP_PASSWORD"]):
        return []
    hours = cfg["email"].get("lookback_hours", 24)
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    digest_subject = cfg["email"].get("digest_subject", "")

    imap = imaplib.IMAP4_SSL("imap.gmail.com")
    try:
        imap.login(s["GMAIL_ADDRESS"], s["GMAIL_APP_PASSWORD"].replace(" ", ""))
        imap.select("INBOX", readonly=True)
        days = max(1, -(-hours // 24))
        query = f"newer_than:{days}d -category:promotions -category:social"
        _, found = imap.search(None, "X-GM-RAW", f'"{query}"')
        ids = found[0].split()[-limit:]

        mail, have_digest = [], False
        for num in reversed(ids):  # newest first
            # BODY.PEEK leaves messages unread.
            _, parts = imap.fetch(num, "(X-GM-LABELS BODY.PEEK[])")
            meta, raw = parts[0]
            msg = email.message_from_bytes(raw)
            subject = _header(msg, "Subject")
            body = _body(msg)

            if digest_subject and subject.startswith(digest_subject):
                if not have_digest:  # only this morning's
                    mail.extend(_unpack_digest(body) or [])
                    have_digest = True
                continue
            try:
                when = parsedate_to_datetime(msg.get("Date"))
            except (TypeError, ValueError):
                when = None
            if when and when.tzinfo and when < since:
                continue
            labels = LABELS.search(meta)
            name, addr = parseaddr(_header(msg, "From"))
            mail.append({
                "account": "personal",
                "sender": name or addr,
                "subject": subject,
                "date": when.isoformat() if when else "",
                "important": bool(labels and b"\\Important" in labels.group(1)),
                "body": body[:1200],
            })
        return mail
    finally:
        try:
            imap.logout()
        except imaplib.IMAP4.error:
            pass
