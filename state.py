"""Tracks what has already been posted so nothing shows up twice.

Two files, both committed back to the repo by the GitHub Action:

  seen.json     every reminder that already went out
  threads.json  which forum post belongs to which program, so later
                reminders reply inside that post instead of making a new one

Entries older than KEEP_DAYS get dropped so the files do not grow forever.
"""

import hashlib
import json
import os
import time

KEEP_DAYS = 400


def key_for(source, identifier):
    raw = f"{source}::{identifier}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _load(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as fh:
            return json.load(fh) or {}
    except (ValueError, OSError):
        print(f"{path} unreadable, starting fresh")
        return {}


class Seen:
    def __init__(self, path="seen.json"):
        self.path = path
        self.data = _load(path)

    def has(self, source, identifier):
        return key_for(source, identifier) in self.data

    def add(self, source, identifier):
        self.data[key_for(source, identifier)] = int(time.time())

    def prune(self):
        cutoff = time.time() - KEEP_DAYS * 86400
        self.data = {k: v for k, v in self.data.items() if v >= cutoff}

    def save(self):
        self.prune()
        with open(self.path, "w") as fh:
            json.dump(self.data, fh, indent=0, sort_keys=True)
        print(f"state: {len(self.data)} entries in {self.path}")


class Threads:
    """Maps "Program name::YYYY-MM-DD" to the Discord forum post for it.

    Keys are readable on purpose. If a post was made before this file
    existed, you can add it by hand: right click the post in Discord,
    Copy Link, and paste the long number at the end as the id.
    """

    def __init__(self, path="threads.json"):
        self.path = path
        self.data = _load(path)

    def get(self, key):
        entry = self.data.get(key)
        if isinstance(entry, dict):
            return str(entry.get("id") or "") or None
        if entry:
            return str(entry)
        return None

    def set(self, key, thread_id):
        self.data[key] = {"id": str(thread_id), "t": int(time.time())}

    def forget(self, key):
        self.data.pop(key, None)

    def save(self):
        cutoff = time.time() - KEEP_DAYS * 86400
        self.data = {
            k: v for k, v in self.data.items()
            if not isinstance(v, dict) or v.get("t", time.time()) >= cutoff
        }
        with open(self.path, "w") as fh:
            json.dump(self.data, fh, indent=1, sort_keys=True)
        print(f"state: {len(self.data)} threads in {self.path}")
