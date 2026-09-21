# Documentation

| document | what it answers |
|---|---|
| [architecture.md](architecture.md) | where the seams are, what runs on which thread, how a turn is cancelled |
| [positioning.md](positioning.md) | what this library is better at, what it refuses to do, and which project to use instead |
| [events.md](events.md) | the seven events, their fields, and what is guaranteed about their order |
| [providers.md](providers.md) | the three protocols, and how to bring your own |
| [turn-taking.md](turn-taking.md) | endpointing, interruption, echo handling |
| [tuning.md](tuning.md) | every threshold, its default, and what it was measured against |
| [client.md](client.md) | the browser client, module by module |
| [benchmarks.md](benchmarks.md) | what the latency report measures, and how to read it |

Every guide here has a Chinese counterpart named `<name>.zh-CN.md`, and this
index has one too: [README.zh-CN.md](README.zh-CN.md). The English page is the
authority, and the two are changed in one commit.

Deciding whether to use this at all? Read [positioning.md](positioning.md);
it names the cases where a bigger stack is the right answer.

New here? Read [architecture.md](architecture.md) first, then
[turn-taking.md](turn-taking.md) - the second one is where the interesting
decisions are, and the ones a reasonable-looking change breaks silently.

Looking for a number? It is in [tuning.md](tuning.md), and the same number is in
`echoturn.config.DIALS`. The module is the authority; the document is checked
against it.
