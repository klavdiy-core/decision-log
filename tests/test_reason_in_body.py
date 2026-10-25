"""A reason written in the commit body counts, not only a `Why:` line (measured 25.10: 33 of 33 AI co-authored
commits in a real repo were reported as saying nothing, though each body explained the change). Red on 0.1.0."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import decide  # noqa: E402

TRAILER = "\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/x\n"
REAL = ("herald 0.14.0: /stop is heard during a turn and kills it\n\n"
        "The last finding of the outside review: one poll thread, so /stop waited for a turn of up to timeout_s\n"
        "that kept spending. Now a watcher keeps polling while a turn runs; /stop is acted on at once." + TRAILER)


class ReasonInBody(unittest.TestCase):
    def test_a_body_that_explains_the_change_says_why(self):
        self.assertTrue(decide.says_why(REAL))
        self.assertTrue(decide.says_why("Fix login\n\nWhy: the token expired after a redirect" + TRAILER))
        self.assertTrue(decide.says_why("Починить вход\n\nТокен истекал после редиректа, поэтому вход падал; "
                                        "теперь он обновляется перед запросом, чтобы сессия не терялась." + TRAILER))

    def test_a_measurement_that_motivates_the_change_says_why(self):
        msg = ("herald 0.5.0: see what it spends and cap it\n\nMeasured on live turns first: a short turn costs "
               "$0.0002 on haiku and $0.0137 on opus; long sessions re-read their history.\n\n- every turn goes "
               "to costs.jsonl" + TRAILER)
        self.assertTrue(decide.says_why(msg))
        what_only = ("herald 0.7.1: /room from Telegram\n\n/room <topic> seats every agent from the config with its "
                     "role, runs the three brainstorm rounds and sends the summary to the chat." + TRAILER)
        self.assertFalse(decide.says_why(what_only))            # what it does, not why: honestly not a reason

    def test_no_body_or_a_list_of_what_changed_does_not(self):
        self.assertFalse(decide.says_why("Update files" + TRAILER))
        self.assertFalse(decide.says_why("Refactor\n\n- moved a\n- renamed b\n- tests" + TRAILER))
        self.assertFalse(decide.says_why("Fix bug\n\nfixed it" + TRAILER))           # too short to be a reason

    def test_the_trailers_themselves_are_not_a_reason(self):
        long_trailers = ("Bump\n\nSigned-off-by: A Person <a@example.com>\nReviewed-by: Someone Else <b@example.com>\n"
                         "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/x\n")
        self.assertFalse(decide.says_why(long_trailers))

    def test_the_hook_accepts_a_reasoned_body(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "MSG")
            with open(p, "w", encoding="utf-8") as f:
                f.write(REAL)
            self.assertEqual(decide.check_message(p, strict=True), 0)


class AddDate(unittest.TestCase):
    def test_add_takes_a_date(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "DECISIONS.md")
            self.assertEqual(decide.main(["-f", p, "add", "Use Postgres", "--why", "two writers",
                                          "--date", "2026-10-19"]), 0)
            self.assertEqual(decide.parse(open(p, encoding="utf-8").read())[0].date, "2026-10-19")
            with self.assertRaises(SystemExit) as cm:                                         # not a date: refused
                decide.main(["-f", p, "add", "x", "--date", "19.10.2026"])
            self.assertEqual(cm.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
