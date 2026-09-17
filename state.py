"""Tracks what has already been posted so nothing shows up twice.

State is a plain JSON file committed back to the repo by the GitHub Action.
Keys older than KEEP_DAYS get dropped so the file does not grow forever.
"""

import hashlib
import json
import os
import time

KEEP_DAYS = 400


def key_for(source, identifier):
    raw = f"{source}::{identifier}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


class Seen:
    def __init__(self, path="seen.json"):
        self.path = path
        self.data = {}
        if os.path.exists(path):
            try:
                with open(path) as fh:
                    self.data = json.load(fh)
            except (ValueError, OSError):
                print("seen.json unreadable, starting fresh")
                self.data = {}

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
