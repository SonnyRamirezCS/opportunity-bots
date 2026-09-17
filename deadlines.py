"""Deadline reminders for the programs listed in programs.yml.

This is the part that matters most for the club. Scrapers break, but a
maintained calendar of the twenty programs Pierce students actually have a
shot at will keep working as long as somebody updates the dates once a year.

Each program fires a reminder when it hits one of the remind_days marks,
and each mark fires only once per cycle.
"""

import datetime as dt


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


def due_reminders(programs, today=None, default_marks=(45, 21, 7, 2)):
    """Yield (program, target_date, days_left, mark) for reminders due now.

    A mark fires when the deadline has come inside it, not only on the exact
    day it crosses. So if the workflow fails for three days, the reminder
    still goes out when it next runs instead of silently disappearing.
    """
    today = today or dt.date.today()

    for prog in programs:
        raw = prog.get("deadline")
        if not raw:
            continue
        deadline = raw if isinstance(raw, dt.date) else dt.date.fromisoformat(str(raw))

        target = _next_occurrence(deadline, prog.get("recurs_annually", True), today)
        if target is None:
            continue

        days_left = (target - today).days
        if days_left < 0:
            continue

        marks = sorted(prog.get("remind_days") or list(default_marks), reverse=True)
        reached = [m for m in marks if m >= days_left]
        if reached:
            yield prog, target, days_left, min(reached)


def build_reminder(prog, target, days_left, role_ids_map, mark=None):
    """Turn a due program into the dict discord_client.build_item expects."""
    mark = days_left if mark is None else mark
    if days_left <= 2:
        urgency = f"Closes in {days_left} day{'s' if days_left != 1 else ''}"
    elif days_left <= 7:
        urgency = f"One week out ({days_left} days)"
    else:
        urgency = f"{days_left} days out"

    fields = [
        ("Deadline", target.strftime("%B %d, %Y"), True),
        ("Countdown", urgency, True),
    ]
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

    footer = prog.get("notes", "")
    if not prog.get("date_confirmed", False):
        footer = (footer + "  " if footer else "") + \
            "Date is from the last cycle and has not been confirmed for this one. Open the link before you plan around it."

    roles = [role_ids_map[r] for r in prog.get("roles", []) if role_ids_map.get(r)]

    return {
        "kind": "deadline",
        "title": prog["name"],
        "url": prog["url"],
        "thread_name": f"{prog['name']} (due {target.strftime('%b %d')})"[:95],
        "description": prog.get("summary"),
        "fields": fields,
        "lead": f"**{urgency}.**",
        "footer": footer or None,
        "role_ids": roles,
        "tag_ids": [],
        "source": "deadlines",
        "id": f"{prog['name']}::{target.isoformat()}::{mark}",
    }
