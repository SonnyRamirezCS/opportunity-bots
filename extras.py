"""Extra posts on top of the daily reminders.

  closed_replies   the day after a deadline, reply "this one is closed" inside
                   its forum post so nobody applies to a dead link
  weekly_digest    Mondays, one message in #announcements listing everything
                   in the next two weeks, linking to each forum post
  officer_checkup  once a month, a to-do list in #task-board: dates that still
                   need checking, and posts that need the Closed tag

None of these ping anyone.
"""

import datetime as dt

import deadlines as dl

EMOJI = {
    "scholarship": "🎓",
    "internship": "💼",
    "research": "🔬",
    "conference": "🎤",
    "talk": "🗣️",
    "transfer": "🏫",
}


def _thread_link(guild_id, thread_id):
    return f"https://discord.com/channels/{guild_id}/{thread_id}"


def _short(d):
    return f"{d:%a} {d:%b} {d.day}"


def _label(prog):
    return prog.get("deadline_label") or ("Date" if dl.category_of(prog) == "talk" else "Deadline")


# --------------------------------------------------------------- closed

def closed_replies(programs, threads, today, grace_days=3):
    """Reply items for real deadlines that passed in the last few days.

    Only things with an actual deadline get this. Talks and "Starts" events
    just end, there is nothing to warn people off.
    """
    out = []
    for prog in programs:
        if _label(prog) != "Deadline":
            continue
        d = dl._as_date(prog.get("deadline"))
        if not d or not (today - dt.timedelta(days=grace_days) <= d < today):
            continue
        key = dl.thread_key(prog, d)
        thread_id = threads.get(key)
        if not thread_id:
            continue

        lines = [f"**This one is closed now.** The deadline was {d:%B} {d.day}."]
        if prog.get("recurs_annually", True):
            lines.append(f"It usually comes back around {d:%B} next year, and the bot "
                         f"will make a new post when it does.")
        lines.append("Officers: add the Closed tag to this post.")
        out.append({
            "kind": "closed",
            "title": prog["name"],
            "url": prog["url"],
            "thread_name": "",
            "description": "\n".join(lines),
            "fields": [],
            "lead": "",
            "footer": None,
            "role_ids": [],
            "tag_ids": [],
            "thread_id": thread_id,
            "source": "closed",
            "id": key,
        })
    return out


# --------------------------------------------------------------- digest

def upcoming(programs, today, days):
    """(target_date, program) for everything landing in the next `days` days."""
    rows = []
    for prog in programs:
        d = dl._as_date(prog.get("deadline"))
        if not d:
            continue
        target = dl._next_occurrence(d, prog.get("recurs_annually", True), today)
        if target is None:
            continue
        if 0 <= (target - today).days <= days:
            rows.append((target, prog))
    rows.sort(key=lambda r: (r[0], r[1]["name"]))
    return rows


def weekly_digest(programs, threads, today, guild_id, forum_id, days=14):
    rows = upcoming(programs, today, days)
    if not rows:
        return None

    lines = []
    for target, prog in rows:
        kind = dl.category_of(prog)
        emoji = EMOJI.get(kind, "📌")
        tid = threads.get(dl.thread_key(prog, target))
        link = _thread_link(guild_id, tid) if (tid and guild_id) else prog["url"]
        label = _label(prog)
        what = "" if label in ("Deadline", "Date") else f" ({label.lower()})"
        lines.append(f"{emoji} `{_short(target)}` [{prog['name']}]({link}){what}")

    intro = "Here's what's due or happening in the next two weeks. Click one for the details."
    outro = f"\nEverything else lives in <#{forum_id}>." if forum_id else ""
    return {
        "kind": "digest",
        "title": f"📅 Coming up: {today:%b} {today.day} to {(today + dt.timedelta(days=days)):%b} {(today + dt.timedelta(days=days)).day}",
        "url": f"https://discord.com/channels/{guild_id}/{forum_id}" if (guild_id and forum_id) else rows[0][1]["url"],
        "thread_name": "",
        "description": intro + "\n\n" + "\n".join(lines) + "\n" + outro,
        "fields": [],
        "lead": "",
        "footer": None,
        "role_ids": [],
        "tag_ids": [],
        "source": "digest",
        "id": f"{today.isocalendar().year}-W{today.isocalendar().week:02d}",
    }


# -------------------------------------------------------------- checkup

def officer_checkup(programs, threads, today, guild_id, repo_url=None, lookahead=75,
                    closed_window=35):
    check = []
    for prog in programs:
        d = dl._as_date(prog.get("deadline"))
        if not d:
            continue
        target = dl._next_occurrence(d, prog.get("recurs_annually", True), today)
        if target is None:
            continue
        rolled = target != d
        confirmed = prog.get("date_confirmed", False) and not rolled
        if not confirmed and 0 <= (target - today).days <= lookahead:
            check.append((target, prog))
    check.sort(key=lambda r: r[0])

    to_close = []
    for prog in programs:
        if _label(prog) != "Deadline":
            continue
        d = dl._as_date(prog.get("deadline"))
        if not d or not (today - dt.timedelta(days=closed_window) <= d < today):
            continue
        tid = threads.get(dl.thread_key(prog, d))
        if tid:
            to_close.append((d, prog, tid))
    to_close.sort(key=lambda r: r[0])

    if not check and not to_close:
        return None

    parts = ["Monthly to-do list from the Opportunity Bot. Takes about 15 minutes."]
    if check:
        parts.append(f"\n**1. Double check these dates** (next {lookahead} days)")
        parts.append("Open each link, find the real date, then fix it in programs.yml "
                     "and set `date_confirmed: true`.")
        for target, prog in check:
            parts.append(f"• `{target:%b} {target.day}` [{prog['name']}]({prog['url']})")
    if to_close:
        n = 2 if check else 1
        parts.append(f"\n**{n}. Add the Closed tag to these posts**")
        for d, prog, tid in to_close:
            parts.append(f"• [{prog['name']}]({_thread_link(guild_id, tid)}) (closed {d:%b} {d.day})")
    if repo_url:
        parts.append(f"\n[Open programs.yml on GitHub]({repo_url.rstrip('/')}/blob/main/programs.yml)")

    desc = "\n".join(parts)
    if len(desc) > 4000:
        desc = desc[:3990].rsplit("\n", 1)[0] + "\n…and more, check programs.yml"

    return {
        "kind": "checkup",
        "title": f"🛠️ Bot check-up for {today:%B}",
        "url": f"{repo_url.rstrip('/')}/blob/main/programs.yml" if repo_url else check[0][1]["url"] if check else to_close[0][1]["url"],
        "thread_name": "",
        "description": desc,
        "fields": [],
        "lead": "",
        "footer": None,
        "role_ids": [],
        "tag_ids": [],
        "source": "checkup",
        "id": f"{today:%Y-%m}",
    }
