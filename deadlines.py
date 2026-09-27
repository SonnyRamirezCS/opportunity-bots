"""Deadline reminders for the programs listed in programs.yml.

This is the part that matters most for the club. Scrapers break, but a
maintained calendar of the programs Pierce students actually have a shot at
will keep working as long as somebody updates the dates once a year.

Each program fires a reminder when it hits one of its remind_days marks, and
each mark fires only once per cycle. The first reminder makes a forum post;
later ones reply inside that same post (run.py handles that part).
"""

import datetime as dt

DEFAULT_MARKS = {
    "talk": (7, 1),
}
FALLBACK_MARKS = (45, 21, 7, 2)


def category_of(prog):
    """internship, research, scholarship, conference or talk."""
    if prog.get("category"):
        return prog["category"]
    tags = prog.get("tags") or []
    return tags[0] if tags else "deadline"


def _as_date(raw):
    if raw is None or raw == "":
        return None
    return raw if isinstance(raw, dt.date) else dt.date.fromisoformat(str(raw))


def _next_occurrence(deadline, recurs, today):
    """Return the upcoming date for this program, rolling a yearly program
    forward if this year's date already passed."""
    if deadline >= today:
        return deadline
    if not recurs:
        return None
    try:
        return deadline.replace(year=deadline.year + 1)
    except ValueError:                             # Feb 29
        return deadline.replace(year=deadline.year + 1, month=3, day=1)


def due_reminders(programs, today=None, default_marks=None):
    """Yield (program, target_date, days_left, mark) for reminders due now,
    most urgent first.

    A mark fires when the deadline has come inside it, not only on the exact
    day it crosses. So if the workflow fails for three days, the reminder
    still goes out when it next runs instead of silently disappearing.
    """
    today = today or dt.date.today()
    due = []

    for prog in programs:
        deadline = _as_date(prog.get("deadline"))
        if not deadline:
            continue

        target = _next_occurrence(deadline, prog.get("recurs_annually", True), today)
        if target is None:
            continue

        days_left = (target - today).days
        if days_left < 0:
            continue

        marks = prog.get("remind_days") or default_marks or \
            DEFAULT_MARKS.get(category_of(prog), FALLBACK_MARKS)
        marks = sorted(marks, reverse=True)
        reached = [m for m in marks if m >= days_left]
        if reached:
            due.append((prog, target, days_left, min(reached)))

    due.sort(key=lambda d: d[2])
    yield from due


def thread_key(prog, target):
    """One forum post per program per cycle."""
    return f"{prog['name']}::{target.isoformat()}"


def _countdown(days_left, is_talk, label="Deadline"):
    if label in ("Deadline",):
        verb = "Closes"
    elif label == "Date":
        verb = "Happening"
    else:
        verb = label                      # "Starts", "Registration opens"
    if days_left == 0:
        return f"{verb} today"
    if days_left == 1:
        return f"{verb} tomorrow" if verb != "Happening" else "Tomorrow"
    if days_left < 7:
        return f"{days_left} days left"
    if days_left == 7:
        return "One week out"
    return f"{days_left} days out"


def _fmt(d):
    return f"{d:%B} {d.day}, {d.year}"


def build_reminder(prog, target, days_left, role_ids_map, mark=None, reply=False):
    """Turn a due program into the dict discord_client expects.

    reply=True builds the short version that goes inside an existing post.
    """
    mark = days_left if mark is None else mark
    kind = category_of(prog)
    is_talk = kind == "talk"
    rolled = _as_date(prog.get("deadline")) != target
    confirmed = prog.get("date_confirmed", False) and not rolled

    label = prog.get("deadline_label") or ("Date" if is_talk else "Deadline")
    urgency = _countdown(days_left, is_talk, label)

    fields = [
        (label, _fmt(target), True),
        ("Countdown", urgency, True),
    ]

    event = _as_date(prog.get("event_date"))
    if not reply:
        if event and not rolled and event != target:
            fields.append(("Event", _fmt(event), True))
        if prog.get("location"):
            fields.append(("Where", prog["location"], True))
        if prog.get("org"):
            fields.append(("Organization", prog["org"], True))
        if prog.get("eligibility"):
            fields.append(("Eligibility", prog["eligibility"], False))
        if prog.get("stipend"):
            fields.append(("Pay", prog["stipend"], True))
        if prog.get("cc_friendly") is not None:
            fields.append(("Community college students",
                           "Eligible" if prog["cc_friendly"] else "Check first, often restricted",
                           True))

    footer = "" if reply else prog.get("notes", "")
    if not confirmed:
        footer = (footer + "  " if footer else "") + \
            "Date is from the last cycle and has not been confirmed for this one. Open the link before you plan around it."

    roles = [role_ids_map[r] for r in prog.get("roles", []) if role_ids_map.get(r)]

    word = {"Deadline": "due ", "Date": ""}.get(label, label.lower() + " ")
    thread_name = f"{prog['name']} ({word}{target:%b} {target.day})"

    return {
        "kind": kind,
        "title": prog["name"],
        "url": prog["url"],
        "thread_name": thread_name[:95],
        "description": None if reply else prog.get("summary"),
        "fields": fields,
        "lead": f"**{urgency}.**" if not reply else f"**Reminder: {urgency[0].lower() + urgency[1:]}.**",
        "footer": footer or None,
        "role_ids": roles,
        "role_names": [r for r in prog.get("roles", []) if role_ids_map.get(r)],
        "tag_ids": [],
        "source": "deadlines",
        "id": f"{prog['name']}::{target.isoformat()}::{mark}",
        "thread_key": thread_key(prog, target),
    }
