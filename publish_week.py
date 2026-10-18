#!/usr/bin/env python3
"""Schedule this week's LinkedIn posts through Publora, in one command.

    python3 publish_week.py --dry-run      # print the schedule, send nothing
    python3 publish_week.py                 # schedule all four
    python3 publish_week.py --print-posts   # print them for copy-paste instead

Self-contained on purpose. The post text lives inside this file, so there is
nothing else to clone, copy or configure. It finds the repo by looking for
`lib/__init__.py` next to it or above it, which is where the credentials in
`.env` and the publishing client in `lib/` live.

Why this is a file you run rather than something fired automatically: a
sandboxed agent often cannot reach api.publora.com at all, and a schedule
that silently fails is worse than no schedule. This prints what it did, and
what went wrong if something did.

Nothing is sent without an explicit --dry-run check first, so the first run
should always be --dry-run.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

IST = timezone(timedelta(hours=5, minutes=30))

#: (weekday, hour, minute, filename, angle, goal). 0 = Monday.
PLAN = [
    (1, 8, 30, "tue-ci-cd-explained.txt", "ci-cd-explained", "saves"),
    (2, 9, 0, "wed-two-different-years.txt", "resume-contradiction", "comments"),
    (3, 9, 30, "thu-thank-you.txt", "named-gratitude", "reposts"),
    (4, 10, 0, "fri-public-test.txt", "public-7-day-test", "comments"),
]

LAUNCH_POST = "4 objects, 1 client, 0 tutorial projects.\n\nI built a real estate CRM in Salesforce. Leads, Accounts, Contacts, Opportunities, and custom objects for the data their business actually runs on.\n\nThirteen Salesforce concepts in that project. Field-level access, sharing rules, role hierarchy, validation rules, workflows, Apex triggers, Visualforce pages, the Data Loader, and test classes.\n\nThat was the build half.\n\nThe half nobody taught me was the release path. Getting that from a sandbox into production without breaking a client's live records. Git for version control, CI/CD through Copado, and a deployment gate that stops a change when the tests do not pass.\n\nThat is the job I actually want. Not the CRM, not the org. The pipeline in between.\n\nI am Copado Salesforce DevOps Certified, and I work on that side of it as an IT intern at Markquery.\n\nThird-year B.E. Computer Science at Sant Gadge Baba University, graduating 2027. Moving toward a team that owns its release tooling the way it owns its code.\n\nI am still learning how you build a pipeline another person can pick up at 2am and trust.\n\nWhat breaks first in a Salesforce pipeline once a team passes ten people?\n\nMangal\n\nP.S. Looking for a DevOps internship or a graduate role. Pune or remote. My email is mangallevharkar@gmail.com."

POSTS = []
POSTS.append((
    "tue-ci-cd-explained.txt",
    "CI/CD explained to kids. 10 terms.\n\nExplanations for kids... and adults!\n\nCI = Continuous Integration. Every time somebody commits code, a computer checks that it still works.\n\nCD = Continuous Delivery. The code gets packed and ready to go out on its own, waiting for a green light.\n\nPipeline = the path the code takes. Commit, build, test, deploy. Every step either passes, or it stops everything.\n\nApex = the programming language Salesforce uses. When a business rule cannot be built with clicks, you write Apex.\n\nTrigger = a piece of Apex that fires when something happens. A record gets created, a field changes, a case closes.\n\nMetadata = everything about your org that is not your data. Fields, layouts, permissions, automation.\n\nDeployment gate = the check that stops a change from going out when the tests did not pass.\n\nRelease = moving a change from a sandbox into production.\n\nVersion control = Git. Every change is a commit, every commit has a history, every history can be rolled back.\n\nEnvironment = a copy of your org. Sandbox for building, staging for testing, production for real users.\n\nThe thing I keep coming back to: in a Salesforce org, metadata is code. It behaves like code, it breaks like code, and it deserves a pipeline like code.\n\nNow you will never forget it.",
))

POSTS.append((
    "wed-two-different-years.txt",
    "In October 2026 I opened a resume I had not read end to end, and the first thing I found was that it did not agree with itself.\n\nThe header said third year. The summary said fourth year. I had copied that summary from a template and never went back to look at the number.\n\nThe second thing I found was a line I had never filled in at all. It said \"Client Details\" and then an arrow pointing at \"Duration\". A template someone else wrote, sitting in the middle of my work, and nobody had ever asked me to delete it.\n\nWhat it cost me was not an interview. It was that I had stopped reading my own document. I would send it and trust it, and trust was the part I had stopped earning.\n\nHere is the honest part. This account has been sitting here empty. Nobody was reading anything from me because I was not writing anything.\n\nSo in October I stopped. I rebuilt the profile around projects instead of coursework. Four objects, thirteen Salesforce concepts, one client pipeline. I read every date and every number before it goes anywhere now.\n\nWhat surprised me: the fix took one evening, and the thing that needed fixing was two words.\n\nWhat is something in yours that you have not read in a while?\n\nMangal",
))

POSTS.append((
    "thu-thank-you.txt",
    "To the Markquery team: thank you for handing a third-year student a real pipeline to work on. You were busy shipping. I asked a lot of questions that week. Nobody made me feel stupid for asking. I noticed that.\n\nTo the engineers I worked with on troubleshooting: thank you for answering why something broke, not just fixing it. That is the only way I learn this. It is why I know what a release gate is for.\n\nTo the client who let me build their real estate CRM: thank you for letting the work be wrong in a sandbox first. It had to be right in production. Four objects and thirteen Salesforce concepts later, that is the part I am proudest of. I got it wrong in a sandbox more often than I got it right.\n\nTo the person at Sant Gadge Baba University who taught me that a good system is one somebody else can pick up: thank you for every time you made me explain it back. I did not enjoy that. It is why I can write a runbook.\n\nTo whoever reads this before I have a job: thank you for reading a third-year student's account with no reason to.\n\nThe pipeline I am trying to get into is not a job title. It is the people willing to let a beginner touch the thing that matters. That is all I am asking for.\n\nMangal",
))

POSTS.append((
    "fri-public-test.txt",
    "Most LinkedIn posts die in the first 30 minutes.\n\nNot because the writing was bad. Because nobody replied in the first hour.\n\nI know this because I watched my own account sit at zero, and because the people whose posts I actually read have something in common. They are not better writers. They are just there in the comments, on day one, saying something useful.\n\nHere is the number I am testing against: 1 reply in the first 60 minutes, from one person who does not know me.\n\nFor the next 7 days I will post one piece of the Salesforce DevOps work I actually did, and I will mark the thing I got wrong while doing it.\n\nYou do two things:\n\n1. Tell me the part that is wrong. \"That is not how it works\" is the reply I am asking for.\n2. If I post something I cannot point at in the project, say so and I will take it down.\n\nIf the thesis is right, I will still be here on day 7 with the receipts. If it is wrong, I owe you a post admitting it. Either way you will know on day 8.\n\nWhat would you want to see me get wrong first?\n\nThird-year Computer Science student, intern at Markquery. I would rather be corrected in public than admired in private.\n\nMangal",
))


def find_repo_root() -> Path:
    """The directory that holds lib/ and .env."""
    here = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd()
    for candidate in [here, *here.parents, Path.cwd(), *Path.cwd().parents]:
        if (candidate / "lib" / "__init__.py").is_file():
            return candidate
    return here


def next_slot(weekday: int, hour: int, minute: int, now: datetime) -> datetime:
    """The next occurrence of that weekday and time, in IST.

    Today counts if the slot has not passed. A slot that already went by
    waits for next week, so running this twice cannot double-post.
    """
    local = now.astimezone(IST)
    days_ahead = (weekday - local.weekday()) % 7
    candidate = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if days_ahead == 0 and candidate <= local:
        days_ahead = 7
    return candidate + timedelta(days=days_ahead)


def print_posts() -> int:
    print("=" * 68)
    print("LAUNCH POST - post this first, as soon as the profile is live")
    print("=" * 68)
    print(LAUNCH_POST)
    for filename, text in POSTS:
        weekday = next(f[0] for f in PLAN if f[3] == filename)
        print()
        print("=" * 68)
        print(filename)
        print("=" * 68)
        print(text)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="print the schedule and exit without calling Publora")
    ap.add_argument("--print-posts", action="store_true",
                    help="print every post so you can paste it in yourself")
    ap.add_argument("--week-of", default="",
                    help="anchor date YYYY-MM-DD; the week containing it is used")
    args = ap.parse_args()

    if args.print_posts:
        return print_posts()

    root = find_repo_root()
    now = datetime.now().astimezone(IST)
    if args.week_of:
        now = datetime.strptime(args.week_of, "%Y-%m-%d").replace(tzinfo=IST)

    by_name = dict((f, t) for f, t in POSTS)
    rows = []
    for weekday, hour, minute, filename, angle, goal in PLAN:
        if filename not in by_name:
            print(f"x missing post: {filename}", file=sys.stderr)
            return 2
        text = by_name[filename]
        rows.append((next_slot(weekday, hour, minute, now), filename, angle, goal, len(text), text))

    rows.sort(key=lambda r: r[0])
    print(f"Schedule ({now.strftime('%Y-%m-%d %H:%M IST')}):\n")
    for when, filename, angle, goal, size, _ in rows:
        utc = when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        print(f"  {when.strftime('%a %d %b %H:%M IST')}  ->  {filename:<30} {size:>5} chars  [{goal}]")
        print(f"      scheduledTime: {utc}")

    if args.dry_run:
        print("\n(dry-run, nothing scheduled)")
        return 0

    sys.path.insert(0, str(root))
    os.chdir(root)
    try:
        from lib import active_backend, publish
    except Exception as exc:
        print(f"x could not import lib/ from {root}: {exc}", file=sys.stderr)
        print("  Run this from inside the linkedin-skills repo.", file=sys.stderr)
        return 2

    backend = active_backend()
    if backend != "publora":
        print(f"x backend is {backend!r}, expected 'publora'.", file=sys.stderr)
        print("  Check PUBLORA_API_KEY and LINKEDIN_PLATFORM_ID in .env, then run:", file=sys.stderr)
        print("    python3 scripts/setup_env.py", file=sys.stderr)
        return 2

    log_path = root / "testing" / "linkedin-routine-log.jsonl"
    ok = True
    for when, filename, angle, goal, size, text in rows:
        utc = when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            resp = publish("post", text, "https://www.linkedin.com/feed/", scheduled_time=utc)
        except Exception as exc:
            print(f"x {filename}: {type(exc).__name__}: {exc}", file=sys.stderr)
            if "SSL" in type(exc).__name__ or "Connection" in type(exc).__name__:
                print("  That is a network error, not a bad key: this machine cannot reach", file=sys.stderr)
                print("  api.publora.com. Check your firewall or proxy, or use --print-posts", file=sys.stderr)
                print("  and paste them into LinkedIn by hand.", file=sys.stderr)
            ok = False
            continue
        r = resp or {}
        post_id = r.get("postGroupId") or r.get("postId") or r.get("id") or "?"
        print(f"OK {filename}: scheduled {utc} (publora id {post_id})")
        log_path.parent.mkdir(exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "date": when.date().isoformat(), "angle": angle, "goal": goal,
                "scheduled_utc": utc, "post_id": post_id, "chars": size,
            }, ensure_ascii=False) + "\n")

    if ok:
        print(f"\nAll {len(rows)} scheduled. They will appear as Scheduled in your Publora")
        print("dashboard. Cancel any of them there before they go out.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
