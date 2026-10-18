#!/usr/bin/env python3
"""Write credentials into .env without them passing through a chat transcript.

Publishing a post to LinkedIn needs a Publora API key. Getting that key into
`.env` is the step where people leak it: paste it into a chat, paste it into a
commit, or `git mv .env.example .env` and push the whole thing. That last one
is not hypothetical - linkedin-skills#28 put a live Publora key and an Apify
token into a public branch, and deleting the file afterwards did not help
because the blob stays reachable at the earlier SHA.

So this script writes the file for you:

    python3 scripts/setup_env.py

It prompts for each credential, masks the secret ones, validates the shape,
and writes `.env` with 0600 permissions. The value never appears on screen and
never lands in a transcript.

Guard rails, because a convenience script that loses a key is worse than no
script at all:

  - Refuses to write if `.env` is tracked by git. A tracked `.env` means a
    future `git add -A` publishes the credential. Fix it with
    `git rm --cached .env` first; the script says so and stops.
  - Backs up an existing `.env` to `.env.bak` before overwriting.
  - Writes atomically, so an interrupted run cannot leave a half-written file.
  - Prints the shape of a credential (prefix and length), never the value.

Exit codes: 0 ok, 1 refused, 2 usage error.
"""
from __future__ import annotations

import getpass
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"

# name, prompt, secret?, validator, one-line description
CREDENTIALS: list[tuple[str, str, bool, re.Pattern[str] | None, str]] = [
    (
        "PUBLORA_API_KEY",
        "Publora API key (from Publora > Settings > API > Create Key)",
        True,
        re.compile(r"^sk_[A-Za-z0-9_.-]{20,}$"),
        "publishes posts, comments and replies to your LinkedIn",
    ),
    (
        "LINKEDIN_PLATFORM_ID",
        "LinkedIn platform id (from Publora > Channels > your LinkedIn channel)",
        False,
        re.compile(r"^linkedin-[A-Za-z0-9]{4,}$"),
        "tells Publora which LinkedIn account to post as",
    ),
    (
        "APIFY_TOKEN",
        "Apify token (from console.apify.com > Settings > Integrations)",
        True,
        re.compile(r"^apify_api_[A-Za-z0-9]{20,}$"),
        "reads post bodies, comment threads and engagers",
    ),
    (
        "PIXFARO_TOKEN",
        "Pixfaro token (name the key 'linkedin', scope Generate)",
        True,
        re.compile(r"^pf_live_[A-Za-z0-9]{16,}$"),
        "generates banners, quote-cards and post images",
    ),
]

TEMPLATE = """\
# Credentials for the linkedin-skills bundle. Written by scripts/setup_env.py.
# This file is gitignored - it never leaves this machine through a push.
#
# Every variable here is OPTIONAL. The skills work in draft-only mode with
# nothing set: they draft, you paste into LinkedIn yourself.
#
# To change a value, re-run:  python3 scripts/setup_env.py
# To remove a credential, delete its line.

# --- Publora: the WRITE side -------------------------------------------
# Signs into your LinkedIn account (do that in the Publora dashboard) and
# publishes approved posts, comments and replies.
#   PUBLORA_API_KEY:   from Publora > Settings > API > Create Key
#   LINKEDIN_PLATFORM_ID: from Publora > Channels > click your channel
{publora_key}
{platform_id}
# --- Apify: the READ side ------------------------------------------------
# Reads post bodies, comment threads, your own recent comments, and the
# people who liked or commented. No LinkedIn login involved.
{apify}
# --- Pixfaro: the IMAGE side ---------------------------------------------
# Generates banners, quote-cards and post illustrations, and stamps your
# brand color or logo on them.
{pixfaro}
"""


def git_tracked_env() -> bool:
    """True when git is tracking a file at the .env path."""
    try:
        out = subprocess.run(
            ["git", "ls-files", "--error-unmatch", ".env"],
            cwd=ROOT, capture_output=True, text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return out.returncode == 0


def read_value(name: str, prompt: str, secret: bool, validator: re.Pattern[str] | None,
               interactive: bool) -> str | None:
    """Ask for one credential. Returns None when the user skips it."""
    while True:
        if interactive:
            raw = (getpass.getpass if secret else input)(f"\n{prompt}\n  > ")
        else:
            raw = sys.stdin.readline()
            if raw == "":
                return None
            raw = raw.strip()
        value = raw.strip().strip("\"'")
        if not value:
            return None
        if validator and not validator.match(value):
            expected = {
                "PUBLORA_API_KEY": "start with 'sk_'",
                "LINKEDIN_PLATFORM_ID": "look like 'linkedin-ABC123DEF'",
                "APIFY_TOKEN": "start with 'apify_api_'",
                "PIXFARO_TOKEN": "start with 'pf_live_'",
            }[name]
            print(f"  That does not look right - it should {expected}.")
            if not interactive:
                return None
            continue
        return value


def render(values: dict[str, str]) -> str:
    def slot(name: str, placeholder: str) -> str:
        value = values.get(name)
        return f"{name}={value}" if value else f"# {name}={placeholder}"

    return TEMPLATE.format(
        publora_key=slot("PUBLORA_API_KEY", "sk_your_key_here"),
        platform_id=slot("LINKEDIN_PLATFORM_ID", "linkedin-your_id_here"),
        apify=slot("APIFY_TOKEN", "apify_api_your_token_here"),
        pixfaro=slot("PIXFARO_TOKEN", "pf_live_your_token_here"),
    )


def write_env(values: dict[str, str]) -> None:
    text = render(values)
    if ENV_PATH.exists():
        # with_name, not with_suffix: Path(".env").suffix is "" (a leading dot
        # is not an extension), so with_suffix would land on ".env.env.bak".
        shutil.copy2(ENV_PATH, ENV_PATH.with_name(".env.bak"))
    fd, tmp = tempfile.mkstemp(dir=str(ROOT), prefix=".env.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.chmod(tmp, 0o600)
        os.replace(tmp, ENV_PATH)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def main() -> int:
    interactive = sys.stdin.isatty()

    if git_tracked_env():
        print("REFUSING to write: git is tracking a file at .env.")
        print()
        print("A tracked .env means one `git add -A` publishes your credentials.")
        print("Fix it first:")
        print()
        print("    git rm --cached .env")
        print()
        print("Then re-run this script. If you already committed it, rotate every")
        print("key in it - the old blobs are still reachable in history.")
        return 1

    print("Setting up credentials in .env")
    print(f"  target: {ENV_PATH}")
    if not interactive:
        print("  (no TTY - reading values from stdin, one per line, in the order below)")

    values: dict[str, str] = {}
    for name, prompt, secret, validator, description in CREDENTIALS:
        print(f"\n{name} - {description}")
        value = read_value(name, prompt, secret, validator, interactive)
        if not value:
            print("  skipped")
            continue
        values[name] = value
        # Print the shape, never the value.
        shown = f"{value[:8]}...{value[-2:]}" if secret else value
        print(f"  ok: {shown}  (len {len(value)})")

    if not values:
        print("\nNothing entered. .env left as it was.")
        return 0

    had_previous = ENV_PATH.exists()
    write_env(values)
    print(f"\nWrote {ENV_PATH} (mode 0600).")
    if had_previous:
        print("Previous version backed up to .env.bak")
    print()
    print("Next:  .venv/bin/python scripts/check_config.py")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nCancelled. .env left as it was.")
        sys.exit(1)
