import io
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from contextlib import redirect_stdout
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import decide  # noqa: E402

LOG = textwrap.dedent("""\
    # Decisions

    ## D-0001 · 2026-10-19 · Use Postgres, not SQLite
    - by: me
    - why: two services write at once
    - rejected: SQLite (one writer); DynamoDB (cost, lock-in)

    ## D-0002 · 2026-10-20 · Retry webhooks 5 times
    - by: ai
    - why:
    - rejected:

    ## D-0003 · 2026-10-21 · Cache user profiles for 60 s
    - by: together
    - why: profile page was 900 ms
    - rejected:

    ## D-0004 · 2026-10-22 · Rename OrderService to Checkout
    - by: ai

    ## D-0005 · 2026-09-01 · Old one
    - by: me
    - why: x
    - rejected: y
    """)


def run(*argv):
    out = io.StringIO()
    with redirect_stdout(out):
        code = decide.main(list(argv))
    return code, out.getvalue()


class Parse(unittest.TestCase):
    def test_reads_entries_and_judges_them(self):
        ds = decide.parse(LOG)
        self.assertEqual([d.id for d in ds], ["D-0001", "D-0002", "D-0003", "D-0004", "D-0005"])
        self.assertEqual([d.kind for d in ds], ["yours", "taken", "half", "taken", "yours"])
        self.assertEqual(ds[0].rejected, ["SQLite (one writer)", "DynamoDB (cost, lock-in)"])

    def test_an_ai_idea_you_weighed_is_yours(self):
        d = decide.parse("## D-0001 · 2026-10-20 · X\n- by: ai\n- why: because\n- rejected: Y (slower)\n")[0]
        self.assertEqual(d.kind, "yours")


class Add(unittest.TestCase):
    def test_add_appends_with_next_id_and_today(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "DECISIONS.md")
            with open(p, "w", encoding="utf-8") as f:
                f.write(LOG)
            code, out = run("-f", p, "add", "Use queues for email", "--why", "SMTP is slow",
                            "--rejected", "threads (lost on deploy)", "--rejected", "cron", "--by", "me")
            self.assertEqual(code, 0)
            self.assertIn("D-0006", out)
            ds = decide.parse(open(p, encoding="utf-8").read())
            self.assertEqual(ds[-1].id, "D-0006")
            self.assertEqual(ds[-1].date, date.today().isoformat())
            self.assertEqual(ds[-1].rejected, ["threads (lost on deploy)", "cron"])
            self.assertEqual(ds[-1].kind, "yours")

    def test_add_creates_the_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "DECISIONS.md")
            run("-f", p, "add", "First", "--by", "ai")
            ds = decide.parse(open(p, encoding="utf-8").read())
            self.assertEqual((ds[0].id, ds[0].kind), ("D-0001", "taken"))

    def test_why_fills_in_a_reason_later(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "DECISIONS.md")
            with open(p, "w", encoding="utf-8") as f:
                f.write(LOG)
            run("-f", p, "why", "D-0002", "the provider drops 1 in 200", "--rejected", "no retries")
            ds = {x.id: x for x in decide.parse(open(p, encoding="utf-8").read())}
            self.assertEqual(ds["D-0002"].why, "the provider drops 1 in 200")
            self.assertEqual(ds["D-0002"].kind, "yours")
            self.assertEqual(ds["D-0001"].why, "two services write at once")   # others untouched


class Review(unittest.TestCase):
    def test_counts_for_the_window(self):
        ds = decide.parse(LOG)
        r = decide.review(ds, since=date(2026, 10, 18), until=date(2026, 10, 24))
        self.assertEqual((r["yours"], r["half"], r["taken"]), (1, 1, 2))
        self.assertEqual([d.id for d in r["to_revisit"]], ["D-0002", "D-0004", "D-0003"])

    def test_cli_review_prints_questions(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "DECISIONS.md")
            with open(p, "w", encoding="utf-8") as f:
                f.write(LOG)
            code, out = run("-f", p, "review", "--since", "2026-10-18", "--until", "2026-10-24", "--no-git")
            self.assertEqual(code, 0)
            self.assertIn("1 yours", out)
            self.assertIn("2 taken", out)
            self.assertIn("Retry webhooks 5 times", out)
            self.assertIn("why", out.lower())


class Git(unittest.TestCase):
    def test_ai_commits_with_and_without_why(self):
        with tempfile.TemporaryDirectory() as root:
            def git(*a, msg=None):
                subprocess.run(["git", "-C", root, *a], check=True, capture_output=True)
            git("init", "-q")
            git("config", "user.email", "t@t")
            git("config", "user.name", "t")
            msgs = [
                "add retries\n\nCo-Authored-By: Claude <noreply@anthropic.com>",
                "switch cache\n\nWhy: profile page was slow\nCo-Authored-By: Claude <noreply@anthropic.com>",
                "fix typo",
                "refactor\n\nCo-authored-by: Copilot <copilot@github.com>",
            ]
            for i, m in enumerate(msgs):
                with open(os.path.join(root, f"f{i}.txt"), "w") as f:
                    f.write(str(i))
                git("add", ".")
                git("commit", "-qm", m)
            g = decide.git_stats(root, since=date(2000, 1, 1))
            self.assertEqual((g["commits"], g["ai"], g["ai_with_why"]), (4, 3, 1))
            self.assertEqual(sorted(g["ai_without_why"]), ["add retries", "refactor"])


class Hook(unittest.TestCase):
    def test_commit_msg_hook_reminds_but_never_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            m = os.path.join(d, "MSG")
            with open(m, "w") as f:
                f.write("do thing\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n")
            err = io.StringIO()
            from contextlib import redirect_stderr
            with redirect_stderr(err):
                self.assertEqual(decide.main(["commit-msg", m]), 0)
            self.assertIn("Why:", err.getvalue())
            with open(m, "w") as f:
                f.write("do thing\n\nWhy: because\nCo-Authored-By: Claude <noreply@anthropic.com>\n")
            err = io.StringIO()
            with redirect_stderr(err):
                decide.main(["commit-msg", m])
            self.assertEqual(err.getvalue(), "")

    def test_strict_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            m = os.path.join(d, "MSG")
            with open(m, "w") as f:
                f.write("do thing\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n")
            from contextlib import redirect_stderr
            with redirect_stderr(io.StringIO()):
                self.assertEqual(decide.main(["commit-msg", m, "--strict"]), 1)


if __name__ == "__main__":
    unittest.main()
