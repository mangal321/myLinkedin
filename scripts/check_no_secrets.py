#!/usr/bin/env python3
"""Fail if a credential, or a file that holds one, is tracked by git.

`.gitignore` is not the safety net people assume. It only stops *untracked*
files from being added, so renaming the tracked `.env.example` to `.env`, which
the GitHub web UI offers as a one-click rename, commits a real `.env` straight
past it. That happened in linkedin-skills#28 and put a live Publora key and an
Apify token into a public branch.

Removing the file in a later commit does not help: the blob stays reachable at
the earlier SHA. The only thing that helps is never committing it.

Usage: python3 scripts/check_no_secrets.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Files that hold credentials by definition, wherever they sit in the tree.
FORBIDDEN_NAMES = re.compile(r"(^|/)\.env(\.[^/]*)?$")
# `.env.example` and `.env.sample` are the documented templates and carry no
# secrets, so they are the one exception.
TEMPLATE_NAMES = re.compile(r"(^|/)\.env\.(example|sample|template)$")

# Real key shapes, with enough trailing entropy to exclude the placeholders that
# appear all over the docs (`sk_your_api_key`, `apify_api_xxx`).
SECRET_PATTERNS = [
    ("Apify token", re.compile(r"\bapify_api_[A-Za-z0-9]{30,}")),
    # Publora keys are `sk_<8 lowercase>_<8 hex>.<64 hex>` - note the dot in
    # the middle. The old pattern wanted one separator followed by a run of
    # alphanumerics with no dot, so it matched no real Publora key at all: the
    # only key shape it could ever have caught was one that does not exist.
    # Since #28 leaked a Publora key, the one pattern that most needed to work
    # was the one that did not. This one accepts the dotted shape and the
    # plain shape, and still refuses the placeholders in the docs
    # (sk_your_key_here, sk_paste_your_key_here, sk_user_to_paste, sk_your_api_key),
    # whose first segment is always under six characters.
    ("Publora API key", re.compile(
        r"\bsk_[A-Za-z0-9]{6,}(?:[._][A-Za-z0-9]{6,})+"
        r"|\bsk_[A-Za-z0-9]{40,}\b")),
    ("Apify token", re.compile(r"\bapify_api_[A-Za-z0-9]{30,}")),
    ("Pixfaro token", re.compile(r"\bpf_live_[A-Za-z0-9]{24,}")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}")),
    ("OpenAI key", re.compile(r"\bsk-(proj-)?[A-Za-z0-9_-]{40,}")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Private key block", re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----")),
]

TEXT_SUFFIXES = {".md", ".py", ".json", ".yml", ".yaml", ".txt", ".sh", ".toml",
                 ".cfg", ".ini", ".env", ".example", ""}


#: Files the user fills with their own material. They ship blank and must stay
#: blank in git: a filled one is personal data, not a secret, so the credential
#: patterns above are blind to it.
PERSONAL_TEMPLATES = re.compile(r"(?:^|/)(voice-profile|story-bank)\.md$")
FILLED_MARKER = re.compile(r"^\s*[-*]?\s*filled:\s*yes\b", re.M | re.I)


def tracked_files() -> list[str]:
    # -z prints paths verbatim, and git stores them as UTF-8.
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT,
                         capture_output=True, encoding="utf-8", check=True).stdout
    return [p for p in out.split("\0") if p]


def skip_worktree_files() -> set[str]:
    """Tracked files the index is told to ignore local edits for.

    `git update-index --skip-worktree` is how a person keeps a filled Voice
    Profile or Story Bank in the working tree without putting it in a commit:
    git stops seeing the local edit, so `git add -A` stages the index version
    (the blank template) and the personal material cannot be committed by
    accident. It is a real protection, not a promise.

    `git ls-files -v` tags each path with a status letter; 'S' is
    skip-worktree, and assume-unchanged shows up as a lowercase 'h'.
    """
    out = subprocess.run(["git", "ls-files", "-v", "-z"], cwd=ROOT,
                         capture_output=True, encoding="utf-8", check=True).stdout
    protected: set[str] = set()
    for entry in out.split("\0"):
        if len(entry) < 3:
            continue
        tag, path = entry[0], entry[2:]
        if tag in ("S", "h"):
            protected.add(path)
    return protected


def main() -> int:
    problems: list[str] = []
    protected = skip_worktree_files()

    for rel in tracked_files():
        if FORBIDDEN_NAMES.match(rel) and not TEMPLATE_NAMES.search(rel):
            problems.append(
                f"{rel}: a .env file is tracked. Untrack it with "
                f"`git rm --cached {rel}`, then rotate anything it held: removing "
                f"it in a later commit leaves the blob reachable in history.")

        path = ROOT / rel
        if path.suffix.lower() not in TEXT_SUFFIXES or not path.is_file():
            continue
        if PERSONAL_TEMPLATES.search(rel):
            # A filled Voice Profile or Story Bank is not a credential, so no
            # pattern below will ever notice it - and it holds a voice
            # fingerprint, client names, salaries, the lot. The templates ship
            # blank and are meant to stay that way in git; fill yours and keep
            # the fill out of a commit.
            #
            # skip-worktree is the supported way to do exactly that: git
            # ignores the local edit, so the filled copy stays on disk for the
            # skills to read and cannot be staged by `git add -A`. A file
            # protected that way is not a leak, so it is reported as protected
            # rather than as a problem.
            try:
                head = path.read_text(encoding="utf-8")[:4000]
            except (UnicodeDecodeError, OSError):
                head = ""
            if FILLED_MARKER.search(head) and rel not in protected:
                problems.append(
                    f"{rel}: this template is marked `filled: yes` and is tracked. "
                    f"It holds your own material, not a credential, so nothing else "
                    f"here would catch it. Keep it out of commits with "
                    f"`git update-index --skip-worktree {rel}`, or restore the blank "
                    f"template with `git checkout {rel}` and keep the filled copy "
                    f"outside the repo.")
            elif FILLED_MARKER.search(head):
                # Protected, so not a problem - but the credential patterns
                # below still run on it. skip-worktree keeps a file out of a
                # commit; it does not make a live key harmless.
                print(f"OK: {rel} is filled but protected with --skip-worktree; "
                      f"git will not commit it.")
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for label, pattern in SECRET_PATTERNS:
            match = pattern.search(text)
            if match:
                line = text[:match.start()].count("\n") + 1
                problems.append(
                    f"{rel}:{line}: looks like a live {label}. If it is real, "
                    f"rotate it now; the value is already in git history.")

    if problems:
        print("Tracked things that should not be in git:\n"
              + "\n".join("  " + p for p in problems))
        return 1

    print(f"OK: {len(tracked_files())} tracked files, no .env and no credential "
          f"patterns.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
