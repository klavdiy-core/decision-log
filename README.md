# decision-log

Keep your judgment visible when an AI writes most of the code.

> RU: страх «ИИ обесценит мою экспертизу» — про то, что решать будет он, а ты только жать Enter. decision-log не спорит со страхом, а меряет: сколько решений за неделю были твоими (причина + отброшенные варианты), сколько наполовину, а сколько ты просто принял.

## What hurts

The code gets written faster than ever. The worry is not the typing. It's that your part shrinks to "looks good, merge": the AI proposes, you accept, and after a few months you notice you can't say why the system is the way it is. Your expertise was the *choosing*, and the choosing went quiet.

You can't fix a feeling with a tool. You can make it visible.

## What it does

A plain `DECISIONS.md` in your repo, one short entry per decision:

```markdown
## D-0001 · 2026-10-19 · Use Postgres, not SQLite
- by: me
- why: two services write at once
- rejected: SQLite (one writer); DynamoDB (cost, lock-in)
```

Each entry is judged by what it contains, not by who proposed it:

| kind | means |
|---|---|
| **yours** | a reason, and the options you turned down. An AI's idea you weighed is yours. |
| **half** | a reason, but nothing weighed against it |
| **taken** | no reason written: accepted, not decided |

`decide review` shows the week:

```
$ decide review
Decisions 2026-10-18 .. 2026-10-24: 2
    1 yours  (a reason and the options you turned down)
    0 half   (a reason, no alternatives weighed)
    1 taken  (no reason written: accepted, not decided)
  50% of this week's decisions are fully yours.
Commits: 1, 1 co-authored by an AI, 0 of them say why.

Worth a second look (answer with: decide why <id> "..." --rejected "..."):
  D-0002  Retry webhooks 5x  (taken, by ai): why this, and what else was possible?

AI co-authored commits that do not say why:
  - retries
```

It also reads `git log`: commits with an AI co-author trailer (Claude, Copilot, Cursor, Codex, Gemini, Aider…) and whether they say why: a `Why:` line (or `Decision: D-000N`), or a body that gives the reason in a sentence or two (at least 15 words besides the subject, lists and trailers, with a word of cause in them: because, so, instead, found, measured...). A body that only says *what* changed does not count. Measured on a real repo whose commits explain themselves in prose: 0 of 33 "said why" while only a `Why:` line counted; now 27 of 33, and the other 6 describe what, not why. An optional commit-msg hook reminds you, gently, when one doesn't. `--strict` makes the reminder a refusal.

Standard library only, Python 3.8+. The log is Markdown: it reads fine on GitHub, and you can edit it by hand.

## Install

```sh
curl -O https://raw.githubusercontent.com/klavdiy-core/decision-log/main/decide.py
python decide.py hook            # optional: the commit-msg reminder (points at this file, so keep it where it is)
```

## Use

```sh
python decide.py add "Use queues for email" --why "SMTP blocks requests" \
    --rejected "threads (lost on deploy)" --rejected "cron (minutes of delay)"
python decide.py add "Retry webhooks 5 times" --by ai      # recorded honestly as taken
python decide.py why D-0002 "the provider drops 1 in 200" --rejected "no retries"
python decide.py review                                   # the last 7 days
python decide.py review --since 2026-10-01
python decide.py list
```

A habit that works: when the assistant proposes something non-trivial, ask it for two alternatives, pick one yourself, and `decide add` with the two you didn't pick. It takes a minute. Your share of "yours" is the number to watch.

## Test

```sh
python -m unittest discover -s tests
```

Parsing and judging entries, adding with the next id, filling in a reason later without touching other entries, the review window and its order, git stats on a real repository with mixed trailers, and the commit-msg hook in reminder and strict modes.

## License

MIT
