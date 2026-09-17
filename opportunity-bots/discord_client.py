"""Posts opportunities to Discord through an incoming webhook.

Works with both forum channels (each opportunity becomes its own post) and
plain text channels. No bot token, no hosting, no gateway connection.
"""

import time
import requests

API_TIMEOUT = 30
COLORS = {
    "internship": 0x5865F2,
    "research": 0x57F287,
    "scholarship": 0xFEE75C,
    "conference": 0xEB459E,
    "deadline": 0xED4245,
}


class DiscordPoster:
    def __init__(self, webhook_url, channel_type="forum", username="Opportunity Bot",
                 avatar_url=None, dry_run=False, pause=2.0):
        self.webhook_url = webhook_url
        self.channel_type = channel_type
        self.username = username
        self.avatar_url = avatar_url
        self.dry_run = dry_run
        self.pause = pause

    def post(self, item):
        """item is a dict built by build_item() below."""
        payload = self._build_payload(item)

        if self.dry_run:
            print("-" * 62)
            print(f"[{item['kind'].upper()}] {item['title']}")
            print(f"  roles: {item.get('role_ids') or 'none'}")
            for field in _normalize_fields(item.get("fields", [])):
                print(f"  {field[0]}: {field[1]}")
            print(f"  {item['url']}")
            return True

        for attempt in range(4):
            resp = requests.post(
                self.webhook_url,
                json=payload,
                params={"wait": "true"},
                timeout=API_TIMEOUT,
            )
            if resp.status_code in (200, 204):
                time.sleep(self.pause)
                return True
            if resp.status_code == 429:
                wait = resp.json().get("retry_after", 5)
                print(f"  rate limited, waiting {wait}s")
                time.sleep(float(wait) + 0.5)
                continue
            print(f"  post failed {resp.status_code}: {resp.text[:300]}")
            return False
        return False

    def _build_payload(self, item):
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
            embed["description"] = item["description"][:1500]
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
        if self.channel_type == "forum":
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
