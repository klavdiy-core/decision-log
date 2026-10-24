#!/usr/bin/env python3
"""decide: keep your judgment visible when an AI writes most of the code.

A plain DECISIONS.md in your repo, one entry per decision: what, why, and what
you turned down. `decide review` tells you, honestly, how many decisions this
week were yours (a reason and rejected options), half yours (a reason, nothing
weighed) and taken (no reason: accepted from the AI, not decided). It also
counts AI co-authored commits that say why. Standard library only.
"""
import argparse
import os
import re
import stat
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta

__version__ = "0.1.0"
DEFAULT_FILE = "DECISIONS.md"
HEAD = re.compile(r"^## (D-\d+) · (\d{4}-\d{2}-\d{2}) · (.+?)\s*$")
FIELD = re.compile(r"^- (by|why|rejected|commit):\s*(.*?)\s*$")
AI_TRAILER = re.compile(
    r"^co-authored-by:.*\b(claude|anthropic|copilot|cursor|codex|openai|gpt|gemini|devin|aider|windsurf|cody)\b"
    r"|generated with \[?(claude code|cursor|copilot)", re.I | re.M)
WHY_TRAILER = re.compile(r"^(why|decision):\s*\S", re.I | re.M)
KINDS = {
    "yours": "a reason and the options you turned down",
    "half": "a reason, no alternatives weighed",
    "taken": "no reason written: accepted, not decided",
}


@dataclass
class Decision:
    id: str
    date: str
    title: str
    by: str = ""
    why: str = ""
    rejected: list = field(default_factory=list)
    commit: str = ""

    @property
    def kind(self):
        if not self.why:
            return "taken"
        return "yours" if self.rejected else "half"


# ---------- file ----------

def parse(text):
    out, cur = [], None
    for line in text.splitlines():
        m = HEAD.match(line)
        if m:
            cur = Decision(*m.groups())
            out.append(cur)
            continue
        f = FIELD.match(line)
        if cur and f:
            k, v = f.groups()
            if k == "rejected":
                cur.rejected = [x.strip() for x in v.split(";") if x.strip()]
            else:
                setattr(cur, k, v)
    return out


def render(d):
    lines = [f"## {d.id} · {d.date} · {d.title}", f"- by: {d.by}", f"- why: {d.why}",
             f"- rejected: {'; '.join(d.rejected)}"]
    if d.commit:
        lines.append(f"- commit: {d.commit}")
    return "\n".join(lines)


def _read(path):
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as f:
        return f.read()


def add(path, title, why="", rejected=(), by="me", commit=""):
    text = _read(path)
    ds = parse(text)
    n = max((int(d.id[2:]) for d in ds), default=0) + 1
    d = Decision(f"D-{n:04d}", date.today().isoformat(), title.strip(), by, why.strip(),
                 [r.strip() for r in rejected if r.strip()], commit)
    if not text.strip():
        text = "# Decisions\n\nOne entry per decision: what, why, and what was turned down.\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(text.rstrip("\n") + "\n\n" + render(d) + "\n")
    return d


def set_why(path, did, why, rejected=()):
    """Fill in the reason (and turned-down options) of an existing entry, leaving the rest of the file alone."""
    text = _read(path)
    blocks = re.split(r"(?m)^(?=## D-\d+ · )", text)
    for i, b in enumerate(blocks):
        ds = parse(b)
        if ds and ds[0].id == did:
            d = ds[0]
            d.why = why.strip()
            d.rejected = d.rejected + [r.strip() for r in rejected if r.strip()]
            tail = "\n".join(l for l in b.splitlines()[1:] if l.strip() and not FIELD.match(l))
            blocks[i] = render(d) + ("\n" + tail if tail else "") + "\n\n"
            with open(path, "w", encoding="utf-8") as f:
                f.write("".join(blocks).rstrip("\n") + "\n")
            return d
    raise KeyError(did)


# ---------- review ----------

def review(decisions, since, until):
    inside = [d for d in decisions if since.isoformat() <= d.date <= until.isoformat()]
    r = {k: sum(1 for d in inside if d.kind == k) for k in KINDS}
    r["total"] = len(inside)
    order = {"taken": 0, "half": 1}
    r["to_revisit"] = sorted((d for d in inside if d.kind != "yours"), key=lambda d: (order[d.kind], d.date, d.id))
    return r


def git_stats(root, since, until=None):
    args = ["git", "-C", root, "log", f"--since={since.isoformat()}", "--format=%s%x1f%B%x1e"]
    if until:
        args.append(f"--until={(until + timedelta(days=1)).isoformat()}")
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        return None
    commits = [c.strip("\n") for c in r.stdout.split("\x1e") if c.strip()]
    ai, with_why, without = 0, 0, []
    for c in commits:
        subject, _, body = c.partition("\x1f")
        if AI_TRAILER.search(body):
            ai += 1
            if WHY_TRAILER.search(body):
                with_why += 1
            else:
                without.append(subject)
    return {"commits": len(commits), "ai": ai, "ai_with_why": with_why, "ai_without_why": without}


def print_review(r, g, since, until):
    print(f"Decisions {since} .. {until}: {r['total']}")
    for k, what in KINDS.items():
        print(f"  {r[k]:>3} {k:<6} ({what})")
    if r["total"]:
        print(f"  {round(100 * r['yours'] / r['total'])}% of this week's decisions are fully yours.")
    if g:
        print(f"Commits: {g['commits']}, {g['ai']} co-authored by an AI, {g['ai_with_why']} of them say why.")
    if r["to_revisit"]:
        print("\nWorth a second look (answer with: decide why <id> \"...\" --rejected \"...\"):")
        for d in r["to_revisit"]:
            q = ("why this, and what else was possible?" if d.kind == "taken"
                 else "what did you turn down, and why?")
            print(f"  {d.id}  {d.title}  ({d.kind}, by {d.by or '?'}): {q}")
    if g and g["ai_without_why"]:
        print("\nAI co-authored commits with no Why: line:")
        for s in g["ai_without_why"][:15]:
            print(f"  - {s}")


# ---------- commit-msg hook ----------

def check_message(path, strict=False):
    with open(path, encoding="utf-8", errors="replace") as f:
        msg = "\n".join(l for l in f.read().splitlines() if not l.startswith("#"))
    if AI_TRAILER.search(msg) and not WHY_TRAILER.search(msg):
        print("decide: this commit is co-authored by an AI and does not say why.\n"
              "        Add a line `Why: <your reason>` (or `Decision: D-000N`) to the message.",
              file=sys.stderr)
        return 1 if strict else 0
    return 0


def install_hook(root, strict=False):
    hooks = os.path.join(root, ".git", "hooks")
    if not os.path.isdir(hooks):
        raise RuntimeError(f"{root} is not the top of a git repository")
    path = os.path.join(hooks, "commit-msg")
    if os.path.exists(path):
        with open(path, encoding="utf-8", errors="replace") as f:
            if "decide" in f.read():
                return path
        raise RuntimeError(f"{path} already exists; add this line to it yourself:\n"
                           f"  python \"{os.path.abspath(__file__)}\" commit-msg \"$1\"{' --strict' if strict else ''}")
    py = "python" if os.name == "nt" else "python3"
    script = os.path.abspath(__file__).replace("\\", "/")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(f'#!/bin/sh\nexec {py} "{script}" commit-msg "$1"{" --strict" if strict else ""}\n')
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


# ---------- CLI ----------

def _day(s):
    return date.fromisoformat(s)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="decide", description=__doc__.splitlines()[0])
    ap.add_argument("-f", "--file", default=DEFAULT_FILE, help=f"the log (default: {DEFAULT_FILE})")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="record a decision")
    a.add_argument("title")
    a.add_argument("-w", "--why", default="")
    a.add_argument("-r", "--rejected", action="append", default=[], help="an option you turned down (repeat)")
    a.add_argument("-b", "--by", default="me", help="me / ai / together / a name")
    a.add_argument("-c", "--commit", default="")

    w = sub.add_parser("why", help="add the reason to a decision later")
    w.add_argument("id")
    w.add_argument("reason")
    w.add_argument("-r", "--rejected", action="append", default=[])

    r = sub.add_parser("review", help="how much of this was decided, and how much taken")
    r.add_argument("--since", type=_day, help="default: 7 days ago")
    r.add_argument("--until", type=_day, help="default: today")
    r.add_argument("--no-git", action="store_true")

    sub.add_parser("list", help="all decisions with their kind")

    c = sub.add_parser("commit-msg", help="(git hook) remind when an AI co-authored commit has no Why:")
    c.add_argument("msgfile")
    c.add_argument("--strict", action="store_true", help="refuse the commit instead of reminding")

    h = sub.add_parser("hook", help="install the commit-msg reminder in this repository")
    h.add_argument("--strict", action="store_true")
    o = ap.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    if o.cmd == "add":
        d = add(o.file, o.title, o.why, o.rejected, o.by, o.commit)
        print(f"{d.id} recorded ({d.kind}) in {o.file}")
        if d.kind != "yours":
            print("  Tip: a decision is yours when it has a reason (--why) and the options you turned down (--rejected).")
        return 0
    if o.cmd == "why":
        try:
            d = set_why(o.file, o.id, o.reason, o.rejected)
        except KeyError:
            print(f"decide: no {o.id} in {o.file}", file=sys.stderr)
            return 2
        print(f"{d.id} is now {d.kind}")
        return 0
    if o.cmd == "review":
        until = o.until or date.today()
        since = o.since or until - timedelta(days=6)
        r = review(parse(_read(o.file)), since, until)
        g = None if o.no_git else git_stats(os.path.dirname(os.path.abspath(o.file)), since, until)
        print_review(r, g, since, until)
        return 0
    if o.cmd == "list":
        for d in parse(_read(o.file)):
            print(f"{d.id}  {d.date}  {d.kind:<6} {d.title}")
        return 0
    if o.cmd == "commit-msg":
        return check_message(o.msgfile, o.strict)
    if o.cmd == "hook":
        try:
            top = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                                 check=True).stdout.strip()
            print(f"installed {install_hook(top, o.strict)}")
        except (subprocess.CalledProcessError, RuntimeError, OSError) as e:
            print(f"decide: {e}", file=sys.stderr)
            return 2
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
