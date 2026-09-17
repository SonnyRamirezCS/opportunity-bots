"""Where opportunities come from.

Two fetchers right now:
  simplify_feed  - the Simplify / Pitt CSC internship JSON list on GitHub
  rss_feed       - any RSS or Atom feed

Both return a list of plain dicts. run.py handles filtering and posting.
"""

import datetime as dt
import re
import time

import feedparser
import requests

USER_AGENT = "PSJC-opportunity-bots/1.0 (Pierce Science Journal Club)"
TIMEOUT = 60


# ---------------------------------------------------------------- Simplify

def simplify_feed(cfg):
    """Internship postings from the SimplifyJobs GitHub list.

    The file is ~13MB of JSON refreshed daily. Schema per entry:
      company_name, title, url, category, terms[], locations[],
      active, is_visible, date_posted (unix), sponsorship, degrees[]
    """
    url = cfg["url"]
    print(f"simplify: fetching {url}")
    resp = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()
    rows = resp.json()
    print(f"simplify: {len(rows)} total listings")

    max_age = cfg.get("max_age_days", 8) * 86400
    now = time.time()
    categories = set(cfg.get("categories", []))
    title_words = [w.lower() for w in cfg.get("title_keywords", [])]
    block_words = [w.lower() for w in cfg.get("title_blocklist", [])]
    location_words = [w.lower() for w in cfg.get("locations", [])]
    terms = set(cfg.get("terms", []))

    out = []
    for row in rows:
        if not (row.get("active") and row.get("is_visible")):
            continue
        posted = row.get("date_posted") or 0
        if now - posted > max_age:
            continue
        if categories and row.get("category") not in categories:
            continue
        if terms and not (terms & set(row.get("terms") or [])):
            continue

        title = (row.get("title") or "").strip()
        low = title.lower()
        if block_words and any(w in low for w in block_words):
            continue
        if title_words and not any(w in low for w in title_words):
            continue

        # Degree gate. An empty list means the posting did not say, so let it
        # through. "Bachelor's" only is fine, PhD-only is not.
        degrees = row.get("degrees") or []
        allowed_degrees = set(cfg.get("degrees", []))
        if degrees and allowed_degrees and not (allowed_degrees & set(degrees)):
            continue

        locations = row.get("locations") or []
        joined = " | ".join(locations).lower()
        blocked_places = [w.lower() for w in cfg.get("location_blocklist", [])]
        if blocked_places and any(_word_in(w, joined) for w in blocked_places):
            continue
        if location_words and not any(_word_in(w, joined) for w in location_words):
            continue

        company = (row.get("company_name") or "Unknown").strip()
        out.append({
            "source": "simplify",
            "id": row.get("id") or row.get("url"),
            "kind": "internship",
            "title": f"{company}: {title}",
            "thread_name": _thread_name(company, title, row.get("terms")),
            "url": row.get("url"),
            "match_text": f"{title} {company}",
            "fields": [
                ("Company", company, True),
                ("Term", ", ".join(row.get("terms") or ["not stated"]), True),
                ("Location", ", ".join(locations[:3]) or "not stated", False),
                ("Sponsorship", row.get("sponsorship") or "not stated", True),
            ],
            "footer": "Via the Simplify / Pitt CSC list. Check the posting for class-standing rules, "
                      "some of these will not take first or second year students.",
            "posted_at": posted,
        })

    print(f"simplify: {len(out)} passed filters")
    return out


def _word_in(needle, haystack):
    """Whole-word match, so the state code CA stops matching Canada."""
    return re.search(r"\b" + re.escape(needle) + r"\b", haystack) is not None


def _thread_name(company, title, terms):
    term = (terms or ["Internship"])[0]
    name = f"{company}: {title} ({term})"
    return re.sub(r"\s+", " ", name)[:95]


# --------------------------------------------------------------------- RSS

def rss_feed(cfg):
    """Any RSS or Atom feed. Handy for lab news pages and program blogs."""
    url = cfg["url"]
    label = cfg.get("label", url)
    print(f"rss: fetching {label}")
    try:
        resp = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
    except Exception as exc:                      # a dead feed should not kill the run
        print(f"rss: {label} failed ({exc})")
        return []

    max_age = cfg.get("max_age_days", 10) * 86400
    keywords = [w.lower() for w in cfg.get("keywords", [])]
    now = time.time()

    out = []
    for entry in parsed.entries[: cfg.get("max_entries", 40)]:
        title = (entry.get("title") or "").strip()
        link = entry.get("link")
        if not (title and link):
            continue

        stamp = entry.get("published_parsed") or entry.get("updated_parsed")
        posted = time.mktime(stamp) if stamp else now
        if now - posted > max_age:
            continue

        summary = re.sub(r"<[^>]+>", " ", entry.get("summary", ""))
        summary = re.sub(r"\s+", " ", summary).strip()

        if keywords and not any(w in (title + " " + summary).lower() for w in keywords):
            continue

        out.append({
            "source": f"rss:{label}",
            "id": entry.get("id") or link,
            "kind": cfg.get("kind", "research"),
            "title": title,
            "thread_name": f"{label}: {title}"[:95],
            "url": link,
            "match_text": f"{title} {summary}",
            "description": summary[:600] or None,
            "fields": [("Source", label, True),
                       ("Posted", _fmt(posted), True)],
            "posted_at": posted,
        })

    print(f"rss: {label} gave {len(out)} items")
    return out


def _fmt(stamp):
    return dt.datetime.fromtimestamp(stamp).strftime("%b %d, %Y")


# ------------------------------------------------------------ role routing

def roles_for(text, role_rules, role_ids):
    """Decide which Discord roles to ping for an item.

    role_rules maps a role name to a list of keywords. A role is pinged only
    when one of its keywords shows up, so nobody gets pinged for everything.
    """
    low = text.lower()
    hits = []
    for role_name, keywords in role_rules.items():
        if any(k.lower() in low for k in keywords):
            rid = role_ids.get(role_name)
            if rid and rid not in hits:
                hits.append(rid)
    return hits


FETCHERS = {
    "simplify": simplify_feed,
    "rss": rss_feed,
}
