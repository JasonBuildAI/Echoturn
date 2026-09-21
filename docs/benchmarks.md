# Benchmarks

Chinese: [benchmarks.zh-CN.md](benchmarks.zh-CN.md)

One script, one question: **how much of a turn's latency is this library's
fault?** It is [`bench/latency.py`](../bench/latency.py), and its module
docstring is the authority on what it does and does not measure. This page is
about reading the output.

```bash
pip install -e ".[dev]"
python bench/latency.py                              # the shipped chunk policy
python bench/latency.py --compare                     # ... beside one that waits
python bench/latency.py --token-ms 25 --compare        # at a model pace worth comparing
python bench/latency.py --json                         # into something else
```

No network, no key, no model files: the providers are the offline ones, so the
numbers are the same with the wifi off.

## The columns

| column | measured from | what moves it |
|---|---|---|
| `first token` | the start of the turn | the time to a `sink` event and a prompt, then whatever the model does before its first piece |
| `first audio` | the start of the turn | everything above, plus how long the first chunk waits before it is worth submitting |
| `total` | the start of the turn | everything above, plus every remaining chunk, and the last sentence's synthesis |
| `chunks` | — | the chunk policy: how many synthesis calls the reply was cut into |

Each cell is `median (p95)` over the runs, in milliseconds. The median is the
number to quote; the p95 is there so that a policy which is usually fine and
occasionally terrible does not look identical to one that is always fine.

## `--token-ms` is not optional if you are comparing policies

The offline model streams its answer instantly. That is convenient and it is
misleading: with an instant model, waiting for the whole reply costs nothing, so
the shipped policy and one that never flushes early measure the same. The
`--token-ms` flag puts a sleep in front of each streamed piece, at which point
the comparison means something — early flushing removes the model's remaining
writing time from time-to-first-audio, and that is exactly what the two rows
differ by.

The pace is printed with every row. A latency number without the pace it was
taken at is not a measurement of anything.

## What the numbers are not

- **Not a prediction.** A hosted model that takes 800 ms to its first token adds
  800 ms to every row. This library cannot know that, and neither can its
  benchmark.
- **Not TTS latency.** The offline voice is a beep synthesised in Python: real
  CPU work, fast in the same direction as a hosted voice and slow by a different
  amount. Compare rows against each other.
- **Not your machine.** Run it where you deploy. The interesting change here is
  usually the direction and the size of a difference, not the absolute figure.

## Adding a benchmark

Two rules, both the same as anywhere else in this repository: measure something
the reader can act on, and print the conditions the number was taken under.
A number without its conditions gets quoted five times and then becomes wrong.
