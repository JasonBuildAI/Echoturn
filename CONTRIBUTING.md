# Contributing to Echoturn

Thanks for taking the time. This project has an unusually small surface area and
unusually high standards, so the fastest way in is to read the two rules below.

## Two rules that matter more than style

1. **A guard must be able to fail.** Every check you add has to come with a way
   to prove it fails: feed it a deliberately bad input in a test and assert the
   red. A check that cannot fail is worse than no check, because it buys false
   confidence.
2. **A documented number must have been measured.** If you write a threshold, a
   latency or a memory figure into code, docs or a comment, say how it was
   obtained. "Should be fine" is not a measurement; if you have not measured it,
   say so in the text instead of inventing a number.

## Development setup

```bash
git clone https://github.com/JasonBuildAI/Echoturn.git
cd Echoturn
python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Optional extras are needed only for the parts you touch:

```bash
pip install "echoturn[vad]"     # local speech detection / endpointing work
pip install "echoturn[web]"     # SSE adapter and the demo page
pip install "echoturn[cli]"     # the microphone/speaker demo
```

## Running the checks

```bash
ruff check .                    # lint and import order
pytest                          # the whole suite, offline
pytest tests/test_text_sentences.py -q   # one module while iterating
node --check clients/echoturn-client.js  # browser client syntax
python scripts/check_privacy.py          # no private identifiers anywhere
```

The suite must pass **without network access** and without any API key. Tests
that need a real provider are marked and never run in CI.

## Commit guidelines

We use [Conventional Commits](https://www.conventionalcommits.org/):
`feat:` `fix:` `perf:` `refactor:` `docs:` `test:` `chore:`.

* One logical change per commit, described in one line, in English.
* A commit must leave the tree green: lint and tests pass at every commit, not
  just at the end of a branch.
* Do not mix an unrelated cleanup into a feature commit.

## Documentation language

Code comments, docstrings and everything under `docs/` are in English. The only
exception is `README.zh-CN.md`, which mirrors the English README. If you change
one README, change the other in the same commit.

## Pull requests

1. Open an issue first for anything that changes a public interface or an event
   shape, so the discussion does not happen after the fact.
2. Keep the diff focused; unrelated refactors belong in their own PR.
3. Describe the behaviour change and the evidence: a test name, a measurement, a
   recording of the event stream. "It works on my machine" is not evidence.
4. If you change a default in `echoturn.config.DIALS`, update `docs/tuning.md` in
   the same PR.

## Reporting bugs

Use the issue templates. For a turn-taking or audio bug, the most useful thing
you can attach is the event stream of one bad turn (`sentence` / `audio` / `done`
lines) plus the values of the knobs you were running with.

## Security

Please do not open a public issue for a vulnerability; see [SECURITY.md](SECURITY.md).
