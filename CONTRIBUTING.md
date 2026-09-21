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
python scripts/check_language.py         # warns about CJK outside the one README
```

The suite must pass **without network access** and without any API key. That is
not a preference: CI has neither, so a test that reaches for a socket fails
there - the fix is to fake the provider, not to mark the test and move on.

When CI goes red, the failing test names are published as annotations on the
run, which anyone can read; the raw log is behind a GitHub sign-in.

## Commit guidelines

We use [Conventional Commits](https://www.conventionalcommits.org/):
`feat:` `fix:` `perf:` `refactor:` `docs:` `test:` `chore:`.

* One logical change per commit, described in one line, in English.
* A commit must leave the tree green: lint and tests pass at every commit, not
  just at the end of a branch.
* Do not mix an unrelated cleanup into a feature commit.

## Documentation language

Code comments, docstrings and everything in `docs/` are in English. Every
English document has a Chinese counterpart whose name ends in `.zh-CN.md`, and
the English one is the authority: the Chinese file says so at the top and lives
in the same commit as the change to its English original.

`scripts/check_language.py` reports every file outside that convention that
contains CJK text and does not fail the build, because the tests use Chinese
punctuation as data.

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
