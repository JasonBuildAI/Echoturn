# Documentation

| document | what it answers |
|---|---|
| [architecture.md](architecture.md) | where the seams are, what runs on which thread, how a turn is cancelled |
| [events.md](events.md) | the seven events, their fields, and what is guaranteed about their order |
| [providers.md](providers.md) | the three protocols, and how to bring your own |
| [turn-taking.md](turn-taking.md) | endpointing, interruption, echo handling |
| [tuning.md](tuning.md) | every threshold, its default, and what it was measured against |
| [client.md](client.md) | the browser client, module by module |
| [benchmarks.md](benchmarks.md) | what the latency report measures, and how to read it |

New here? Read [architecture.md](architecture.md) first, then
[turn-taking.md](turn-taking.md) - the second one is where the interesting
decisions are, and the ones a reasonable-looking change breaks silently.

Looking for a number? It is in [tuning.md](tuning.md), and the same number is in
`echoturn.config.DIALS`. The module is the authority; the document is checked
against it.
