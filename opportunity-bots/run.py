#!/usr/bin/env python3
"""opportunity-bots

Posts internships, REUs, scholarships and conference calls into the PSJC
Discord, pinging only the roles the item is relevant to.

  python run.py --dry-run          print what it would post, send nothing
  python run.py --only deadlines   run one section
  python run.py                    the real thing
"""

import argparse
import datetime as dt
import os
import sys

import yaml

import deadlines as deadlines_mod
import sources as sources_mod
from discord_client import DiscordPoster, build_item
from state import Seen


def load_yaml(path):
    with open(path) as fh:
        return yaml.safe_load(fh) or {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yml")
    ap.add_argument("--programs", default="programs.yml")
    ap.add_argument("--dry-run", action="store_true",
                    help="print instead of posting, and do not touch seen.json")
    ap.add_argument("--only", choices=["feeds", "deadlines"],
                    help="run only one half")
    ap.add_argument("--limit", type=int,
                    help="override max posts for this run")
    args = ap.parse_args()

    cfg = load_yaml(args.config)
    webhook = os.environ.get("DISCORD_WEBHOOK_URL", "")

    if not webhook and not args.dry_run:
        sys.exit("DISCORD_WEBHOOK_URL is not set. Add it as a repo secret, "
                 "or run with --dry-run to test without it.")

    poster = DiscordPoster(
        webhook_url=webhook,
        channel_type=cfg.get("channel_type", "forum"),
        username=cfg.get("bot_username", "Opportunity Bot"),
        avatar_url=cfg.get("bot_avatar_url"),
        dry_run=args.dry_run,
        pause=cfg.get("seconds_between_posts", 2.0),
    )

    seen = Seen(cfg.get("state_file", "seen.json"))
    role_ids = {k: str(v) for k, v in (cfg.get("role_ids") or {}).items() if v}
    role_rules = cfg.get("role_keywords") or {}
    tag_ids = cfg.get("forum_tag_ids") or {}

    max_posts = args.limit or cfg.get("max_posts_per_run", 8)
    posted = 0
    queue = []

    # ---- deadline reminders first, they are the ones worth seeing
    if args.only in (None, "deadlines"):
        programs = load_yaml(args.programs).get("programs", [])
        print(f"\n== deadlines ({len(programs)} programs tracked)")
        for prog, target, days_left, mark in deadlines_mod.due_reminders(programs):
            item = deadlines_mod.build_reminder(prog, target, days_left, role_ids, mark)
            if seen.has(item["source"], item["id"]):
                continue
            item["tag_ids"] = _tags_for(prog.get("tags", []), tag_ids)
            queue.append(item)
        print(f"== deadlines: {len(queue)} due today")

    # ---- feed items
    if args.only in (None, "feeds"):
        feed_items = []
        for feed_cfg in cfg.get("feeds", []):
            if not feed_cfg.get("enabled", True):
                continue
            fetcher = sources_mod.FETCHERS.get(feed_cfg.get("type"))
            if not fetcher:
                print(f"unknown feed type {feed_cfg.get('type')}, skipping")
                continue
            try:
                feed_items.extend(fetcher(feed_cfg))
            except Exception as exc:
                print(f"feed {feed_cfg.get('label', feed_cfg.get('type'))} failed: {exc}")

        feed_items.sort(key=lambda x: x.get("posted_at", 0), reverse=True)

        for raw in feed_items:
            if seen.has(raw["source"], raw["id"]):
                continue
            roles = sources_mod.roles_for(raw.get("match_text", raw["title"]),
                                          role_rules, role_ids)
            if cfg.get("require_role_match", False) and not roles:
                continue
            queue.append(build_item(
                kind=raw["kind"],
                title=raw["title"],
                url=raw["url"],
                thread_name=raw["thread_name"],
                fields=raw.get("fields", []),
                description=raw.get("description"),
                footer=raw.get("footer"),
                role_ids=roles,
                tag_ids=_tags_for([raw["kind"]], tag_ids),
            ) | {"source": raw["source"], "id": raw["id"]})

    print(f"\n== {len(queue)} item(s) queued, posting up to {max_posts}")

    for item in queue[:max_posts]:
        ok = poster.post(item)
        if ok:
            posted += 1
            if not args.dry_run:
                seen.add(item["source"], item["id"])

    skipped = max(0, len(queue) - max_posts)
    if skipped:
        print(f"{skipped} item(s) held back for tomorrow so the channel does not flood")

    if not args.dry_run:
        seen.save()

    print(f"\ndone {dt.datetime.now():%Y-%m-%d %H:%M}: posted {posted}")


def _tags_for(names, tag_ids):
    return [str(tag_ids[n]) for n in names if tag_ids.get(n)]


if __name__ == "__main__":
    main()
