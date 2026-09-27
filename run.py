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
import extras
import sources as sources_mod
from discord_client import DiscordPoster, build_item
from state import Seen, Threads


def load_yaml(path):
    with open(path) as fh:
        return yaml.safe_load(fh) or {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yml")
    ap.add_argument("--programs", default="programs.yml")
    ap.add_argument("--dry-run", action="store_true",
                    help="print instead of posting, and do not touch seen.json")
    ap.add_argument("--only", choices=["feeds", "deadlines", "closed", "digest", "checkup"],
                    help="run only one part")
    ap.add_argument("--force-extras", action="store_true",
                    help="post the digest and check-up now, ignoring the schedule")
    ap.add_argument("--today", help="pretend today is YYYY-MM-DD (for testing)")
    ap.add_argument("--limit", type=int,
                    help="override max posts for this run")
    args = ap.parse_args()

    cfg = load_yaml(args.config)
    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    programs = load_yaml(args.programs).get("programs", [])
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
    threads = Threads(cfg.get("threads_file", "threads.json"))
    role_ids = {k: str(v) for k, v in (cfg.get("role_ids") or {}).items() if v}
    role_rules = cfg.get("role_keywords") or {}
    tag_ids = cfg.get("forum_tag_ids") or {}

    max_posts = args.limit or cfg.get("max_posts_per_run", 8)
    posted = 0
    queue = []

    # ---- "this one is closed" replies for deadlines that just passed
    if args.only in (None, "closed"):
        for item in extras.closed_replies(programs, threads, today):
            if not seen.has(item["source"], item["id"]):
                queue.append(item)
        print(f"\n== closed: {len(queue)} post(s) to mark closed")

    # ---- deadline reminders, the ones worth seeing
    if args.only in (None, "deadlines"):
        print(f"\n== deadlines ({len(programs)} programs tracked)")
        before = len(queue)
        for prog, target, days_left, mark in deadlines_mod.due_reminders(programs, today):
            full = deadlines_mod.build_reminder(prog, target, days_left, role_ids, mark)
            if seen.has(full["source"], full["id"]):
                continue
            names = _tag_names_for(prog)
            full["tag_names"] = names
            full["tag_ids"] = _tags_for(names, tag_ids)

            existing = threads.get(full["thread_key"])
            if existing:
                # Already has a post this cycle, so reply inside it.
                item = deadlines_mod.build_reminder(prog, target, days_left,
                                                    role_ids, mark, reply=True)
                item["thread_id"] = existing
                item["_new_post"] = full        # fallback if that post is gone
            else:
                item = full
            queue.append(item)
        print(f"== deadlines: {len(queue) - before} due today")

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
        result = poster.post(item)
        if not result and result.thread_missing and item.get("_new_post"):
            print("  that post seems to be gone, starting a new one")
            threads.forget(item["thread_key"])
            item = item["_new_post"]
            result = poster.post(item)
        if result:
            posted += 1
            if not args.dry_run:
                seen.add(item["source"], item["id"])
                if item.get("thread_key") and result.thread_id and not item.get("thread_id"):
                    threads.set(item["thread_key"], result.thread_id)

    skipped = max(0, len(queue) - max_posts)
    if skipped:
        print(f"{skipped} item(s) held back for tomorrow so the channel does not flood")

    # ---- weekly digest and monthly check-up, in their own channels
    guild_id = str(cfg.get("guild_id") or "")
    forum_id = str(cfg.get("forum_channel_id") or "")
    extras_cfg = cfg.get("extras") or {}

    if args.only in (None, "digest"):
        dcfg = extras_cfg.get("weekly_digest") or {}
        digest = extras.weekly_digest(programs, threads, today, guild_id, forum_id,
                                      days=dcfg.get("days_ahead", 14))
        on_schedule = 0 <= today.weekday() - dcfg.get("weekday", 0) <= 2
        posted += _post_extra("weekly digest", digest, dcfg, on_schedule, args, cfg, seen)

    if args.only in (None, "checkup"):
        ccfg = extras_cfg.get("officer_checkup") or {}
        checkup = extras.officer_checkup(programs, threads, today, guild_id,
                                         repo_url=cfg.get("repo_url"),
                                         lookahead=ccfg.get("days_ahead", 75))
        on_schedule = today.day >= ccfg.get("day_of_month", 1)
        posted += _post_extra("officer check-up", checkup, ccfg, on_schedule, args, cfg, seen)

    if not args.dry_run:
        seen.save()
        threads.save()

    print(f"\ndone {dt.datetime.now():%Y-%m-%d %H:%M}: posted {posted}")


def _post_extra(label, item, section_cfg, on_schedule, args, cfg, seen):
    """Post the digest or check-up to its own text channel, once per period."""
    print(f"\n== {label}")
    if not section_cfg.get("enabled", True):
        print("  turned off in config.yml")
        return 0
    if item is None:
        print("  nothing to post")
        return 0
    if not args.force_extras:
        if not on_schedule:
            print("  not scheduled today")
            return 0
        if seen.has(item["source"], item["id"]):
            print("  already posted this period")
            return 0

    env = section_cfg.get("webhook_secret", "")
    url = os.environ.get(env, "") if env else ""
    if not url and not args.dry_run:
        print(f"  {env} is not set, skipping. Add it as a repo secret to turn this on.")
        return 0

    poster = DiscordPoster(
        webhook_url=url,
        channel_type="text",
        username=cfg.get("bot_username", "Opportunity Bot"),
        avatar_url=cfg.get("bot_avatar_url"),
        dry_run=args.dry_run,
        pause=cfg.get("seconds_between_posts", 2.0),
    )
    result = poster.post(item)
    if result and not args.dry_run:
        seen.add(item["source"], item["id"])
    return 1 if result else 0


def _tags_for(names, tag_ids):
    return [str(tag_ids[n]) for n in names if tag_ids.get(n)][:5]


def _tag_names_for(prog):
    """The program's own tags, plus its category, plus Deadline for anything
    you have to apply or submit for. Talks are just events, so no Deadline."""
    kind = deadlines_mod.category_of(prog)
    names = [kind] + list(prog.get("tags") or [])
    if kind != "talk":
        names.append("deadline")
    return list(dict.fromkeys(names))


if __name__ == "__main__":
    main()
