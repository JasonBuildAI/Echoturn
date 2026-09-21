# 文档

**English: [README.md](README.md)** —— 英文版是唯一真源，本页是它的中文对照。
两版不一致时以英文版为准；改英文版时要同一个 commit 改这一页。

| 文档 | 它回答什么 |
|---|---|
| [architecture.zh-CN.md](architecture.zh-CN.md) | 接缝在哪、哪条线程在跑什么、一轮怎么被取消 |
| [events.zh-CN.md](events.zh-CN.md) | 七个事件、各自的字段，以及它们的顺序里哪些是有保证的 |
| [providers.zh-CN.md](providers.zh-CN.md) | 三个协议，以及怎么接自己的 |
| [turn-taking.zh-CN.md](turn-taking.zh-CN.md) | 断句、打断、回声处理 |
| [tuning.zh-CN.md](tuning.zh-CN.md) | 每一个阈值、它的默认值，以及它是对着什么量出来的 |
| [client.zh-CN.md](client.zh-CN.md) | 浏览器客户端，逐个模块 |
| [benchmarks.zh-CN.md](benchmarks.zh-CN.md) | 延迟报告量的是什么，以及怎么读 |

刚上手？先读 [architecture.zh-CN.md](architecture.zh-CN.md)，再读
[turn-taking.zh-CN.md](turn-taking.zh-CN.md) —— 有意思的决定都在第二份里，而它们正是被
「看起来没问题」的改动悄悄弄坏的那些。

在找一个数字？它在 [tuning.zh-CN.md](tuning.zh-CN.md) 里，同一个数字也在
`echoturn.config.DIALS` 里。**模块是权威**，文档是被拿去和它对账的那一份。
