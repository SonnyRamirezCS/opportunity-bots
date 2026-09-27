"""Posts opportunities to Discord through an incoming webhook.

Works with both forum channels (each opportunity becomes its own post) and
plain text channels. No bot token, no hosting, no gateway connection.

In a forum channel, an item with a thread_id gets posted as a reply inside
that existing post instead of starting a new one. Replying also bumps the
post back to the top of the forum, so people still see it.
"""

import time
import requests

API_TIMEOUT = 30
COLORS = {
    "internship": 0x5865F2,
    "research": 0x57F287,
    "scholarship": 0xFEE75C,
    "conference": 0xEB459E,
    "talk": 0x3BA55C,
    "transfer": 0x00A8FC,
    "digest": 0x5865F2,
    "checkup": 0xF0B232,
    "closed": 0x4E5058,
    "deadline": 0xED4245,
}


class PostResult:
    def __init__(self, ok, thread_id=None, thread_missing=False):
        self.ok = ok
        self.thread_id = thread_id
        self.thread_missing = thread_missing

    def __bool__(self):
        return self.ok


class DiscordPoster:
    def __init__(self, webhook_url, channel_type="forum", username="Opportunity Bot",
                 avatar_url=None, dry_run=False, pause=2.0):
        self.webhook_url = webhook_url
        self.channel_type = channel_type
        self.username = username
        self.avatar_url = avatar_url
        self.dry_run = dry_run
        self.pause = pause
        self._fake_thread = 0

    def post(self, item):
        """item is a dict built by build_item() below. Returns a PostResult."""
        reply_to = item.get("thread_id") if self.channel_type == "forum" else None
        payload = self._build_payload(item, reply_to)

        if self.dry_run:
            print("-" * 62)
            where = f"REPLY in post {reply_to}" if reply_to else "NEW POST"
            print(f"[{item['kind'].upper()}] {where}: {item['title']}")
            if not reply_to and self.channel_type == "forum":
                print(f"  post title: {payload.get('thread_name')}")
                print(f"  tags: {item.get('tag_names') or 'none'}"
                      f"{'' if item.get('tag_ids') else '  (no tag IDs set yet)'}")
            print(f"  roles: {item.get('role_names') or item.get('role_ids') or 'none'}")
            if item.get("lead"):
                print(f"  {item['lead']}")
            if item.get("description") and item["kind"] in ("digest", "checkup", "closed"):
                print("  " + item["description"].replace("\n", "\n  "))
            for field in _normalize_fields(item.get("fields", [])):
                print(f"  {field[0]}: {field[1]}")
            if item.get("footer"):
                print(f"  note: {item['footer']}")
            print(f"  {item['url']}")
            self._fake_thread += 1
            return PostResult(True, thread_id=reply_to or f"dry-run-{self._fake_thread}")

        params = {"wait": "true"}
        if reply_to:
            params["thread_id"] = str(reply_to)

        for _ in range(4):
            resp = requests.post(self.webhook_url, json=payload, params=params,
                                 timeout=API_TIMEOUT)
            if resp.status_code in (200, 204):
                time.sleep(self.pause)
                thread_id = reply_to
                if not thread_id and resp.status_code == 200:
                    try:
                        # For a new forum post, the message lives in the new
                        # thread, so its channel_id is the post's id.
                        thread_id = resp.json().get("channel_id")
                    except ValueError:
                        thread_id = None
                return PostResult(True, thread_id=thread_id)
            if resp.status_code == 429:
                try:
                    wait = float(resp.json().get("retry_after", 5))
                except ValueError:
                    wait = 5.0
                print(f"  rate limited, waiting {wait}s")
                time.sleep(wait + 0.5)
                continue
            print(f"  post failed {resp.status_code}: {resp.text[:300]}")
            # If the post we were replying to got deleted or locked, tell the
            # caller so it can start a fresh post instead.
            return PostResult(False, thread_missing=bool(reply_to) and 400 <= resp.status_code < 500)
        return PostResult(False)

    def _build_payload(self, item, reply_to=None):
        embed = {
            "title": item["title"][:250],
            "url": item["url"],
            "color": COLORS.get(item["kind"], 0x99AAB5),
            "fields": [
                {"name": name, "value": str(value)[:1020], "inline": inline}
                for name, value, inline in _normalize_fields(item.get("fields", []))
            ],
        }
        if item.get("description"):
            embed["description"] = item["description"][:4000]
        if item.get("footer"):
            embed["footer"] = {"text": item["footer"][:2040]}

        role_ids = item.get("role_ids") or []
        mentions = " ".join(f"<@&{rid}>" for rid in role_ids)
        content = (mentions + " " + item.get("lead", "")).strip()

        payload = {
            "username": self.username,
            "embeds": [embed],
            "allowed_mentions": {"parse": [], "roles": [str(r) for r in role_ids]},
        }
        if content:
            payload["content"] = content[:1900]
        if self.avatar_url:
            payload["avatar_url"] = self.avatar_url
        if self.channel_type == "forum" and not reply_to:
            payload["thread_name"] = item["thread_name"][:95]
            if item.get("tag_ids"):
                payload["applied_tags"] = [str(t) for t in item["tag_ids"]][:5]
        return payload


def _normalize_fields(fields):
    out = []
    for f in fields:
        if len(f) == 3:
            out.append(f)
        else:
            out.append((f[0], f[1], True))
    return out[:25]


def build_item(kind, title, url, thread_name, fields=None, description=None,
               lead="", footer=None, role_ids=None, tag_ids=None):
    return {
        "kind": kind,
        "title": title,
        "url": url,
        "thread_name": thread_name,
        "fields": fields or [],
        "description": description,
        "lead": lead,
        "footer": footer,
        "role_ids": role_ids or [],
        "tag_ids": tag_ids or [],
    }
