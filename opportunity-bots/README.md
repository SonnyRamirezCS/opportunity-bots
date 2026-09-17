# opportunity-bots

Posts internships, REUs, scholarships and conference deadlines into the PSJC
Discord, and pings only the major roles each one is actually relevant to.

Runs on GitHub Actions once a day. No server, no bot token, no hosting bill,
nothing to keep alive in the homelab.

## What it posts

**Deadline reminders** from `programs.yml`, a hand kept calendar of the
programs Pierce students can realistically get into: DOE CCI, NASA OSTEM,
NCAS, JPL, NSF REU season, Jack Kent Cooke transfer scholarship, SACNAS and
so on. Each program fires at 45, 21, 7 and 2 days out. About 2 to 3 posts a
week. This half depends on nobody else's website staying up.

**Industry internship postings** from the Simplify and Pitt CS club list are
built in but turned off. Most of those roles expect juniors and seniors at
four year schools, so at launch they would bury the programs our members can
actually get. To turn it on later, set `enabled: true` on the simplify feed in
`config.yml`. The location filter is already narrowed to LA and the South Bay.

Each post goes in as its own forum thread with the deadline, eligibility,
whether community college students qualify, and the link.

## Setup

**1. Push this to the repo**

```bash
git add .
git commit -m "opportunity bot v1"
git push
```

**2. Make the Discord webhook**

In Discord, open the channel you want, click the gear, go to Integrations,
then Webhooks, then New Webhook. Name it Opportunity Bot, then Copy Webhook
URL.

That URL is a password. Anyone who has it can post to that channel. It goes
in GitHub secrets, never in a file you commit.

**3. Add it as a repo secret**

Repo on GitHub, Settings, Secrets and variables, Actions, New repository
secret. Name it exactly `DISCORD_WEBHOOK_URL` and paste the URL.

**4. Get your role IDs**

Turn on Developer Mode first: User Settings, Advanced, Developer Mode.

Then Server Settings, Roles, click a role, three dots, Copy Role ID. Do that
for Physics, Engineering, Bio, Chem and CS, and paste each into `role_ids` in
`config.yml`. Leave one blank and it just never gets pinged.

**5. Test it before it can embarrass you**

On GitHub: Actions tab, "Post opportunities", Run workflow, leave the dry run
box checked. It prints everything it would have posted and sends nothing.
Read that output and see if it looks right.

Locally it is the same thing:

```bash
pip install -r requirements.txt
python run.py --dry-run
```

**6. Turn it on**

Once the dry run looks right, it runs itself every morning at 8 AM Pacific.
To post immediately, run the workflow again with the dry run box unchecked.

## Running it on the home server instead

GitHub Actions is the easy start, but nothing here depends on it. The script
is plain Python with three libraries and it writes its own state to a file, so
moving it to the mini PC is a copy and a cron line.

```bash
git clone <your repo url> ~/opportunity-bots
cd ~/opportunity-bots
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
echo 'DISCORD_WEBHOOK_URL=paste_it_here' > .env
chmod 600 .env
```

Then `crontab -e` and add one line for 8 AM daily:

```
0 8 * * * cd ~/opportunity-bots && set -a && . ./.env && set +a && .venv/bin/python run.py >> bot.log 2>&1
```

Two things change when you move it. The Action commits `seen.json` back to
GitHub after each run, so pick one home or the other and do not run both at
once or they will fight over that file. And the machine has to be awake at
8 AM, which Actions never has to worry about.

Worth doing if you want to add sources that need scraping, a local database,
or anything that would leak a secret into a public repo. Not worth doing just
to run this as it stands.

## Tuning it

Almost everything lives in `config.yml`.

- Channel is a plain text channel, not a forum? Set `channel_type: text`.
- Too many posts? Lower `max_posts_per_run`, or trim `title_keywords`.
- Too few? Empty out `locations` to go nationwide, or add categories.
- Want only things tied to a major? Set `require_role_match: true`.

Anything held back by the cap is not lost, it goes out the next morning.

## The part that needs a human

Every date in `programs.yml` is the typical window from a previous cycle, not
a confirmed date. That is why `date_confirmed: false` is set on all of them,
and why the bot adds a "confirm this on the site" line to those reminders.

Once a semester, sit down for twenty minutes, open each program's page, fix
the dates, and flip `date_confirmed: true` on the ones you checked. That is
the whole maintenance burden. Put it in the officer handoff doc so the next
president knows it is their job.

## Files

| File | What it does |
|---|---|
| `run.py` | entry point, ties everything together |
| `config.yml` | roles, filters, feeds, caps |
| `programs.yml` | the deadline calendar you maintain |
| `sources.py` | fetchers for the Simplify list and any RSS feed |
| `deadlines.py` | works out which reminders are due |
| `discord_client.py` | builds and sends the webhook post |
| `state.py` | `seen.json`, so nothing posts twice |

## Notes

The Action commits `seen.json` back to the repo after each run. That is how it
remembers what it already posted. If you ever want it to re-post everything,
empty that file back to `{}`.

If a reminder gets missed because the workflow failed, it still goes out on the
next successful run. Marks trigger on "the deadline is now inside this window",
not on one exact day.
