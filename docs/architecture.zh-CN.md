# 架构

**English: [architecture.md](architecture.md)** —— 英文版是唯一真源，本页是它的中文对照。
两版不一致时以英文版为准；改英文版时要**同一个 commit** 改这一页。

Echoturn 是一条流水线、三个接缝。接缝是宿主会替换掉的部分，其余部分就是「不值得重写」
的那部分。

| 接缝 | 里面是什么 | 替换的代价 |
|---|---|---|
| providers | 语音识别、语音合成、文本生成 | 每个一个协议，不要求继承基类 |
| transport | 一轮的事件怎么送到客户端 | 一个函数：`echoturn.integrations.starlette.sse_response` |
| conversation window | 一轮能拿到哪些近期上下文 | 两个方法：`window`、`append` |

## 模块地图

| 模块 | 负责什么 | 需要什么 |
|---|---|---|
| `echoturn.text` | 把模型输出变成值得念出口的东西 | 无 |
| `echoturn.audio` | PCM/WAV 容器、重采样、音高、语速 | 音高与语速要 `numpy` |
| `echoturn.vad` | 这是人声吗，有多少 | `numpy`，用模型还要 `onnxruntime` |
| `echoturn.endpoint` | 这句说完了吗 | `numpy`、`onnxruntime` |
| `echoturn.providers` | ASR/TTS/LLM 适配器，含离线 mock | 走 HTTP 的那几个要 `httpx` |
| `echoturn.pipeline` | 一轮：从文本到有序音频片 | 无 |
| `echoturn.store` | 近期消息窗口，以及一个实现 | 无 |
| `echoturn.integrations` | 把一轮以 SSE 送出去 | `starlette` |
| `echoturn.cli` | 终端里的一场对话 | 要出声还要 `sounddevice` |

核心只依赖 `httpx`，别的都不要。流水线的导入路径里没有 Web 框架，一轮纯文字里没有数值
计算库，一个服务端进程里没有声卡。只想拿自己的模型跑几轮的人，装一个包，其余一概不用装。

## 一轮

```
TurnInput ──► 拼提示词（系统提示 + 上下文 + 这条消息）
                  │
                  ▼
              LLMClient.stream ──► 片段 ──► 句子 ──┬──► sentence 事件
                  （自己占一条线程）                │
                                                    └──► 攒句 ──► TTS 线程池
                                                                          │
                                                      audio 事件 ◄────────┘
                                                      （按 idx 排序）
```

三件事同时在跑，整个设计难点就这一个：

1. 模型还在写；
2. 第三片已经合成完了；
3. 第二片还没好。

事件是生成器而不是回调，所以「暂时压住多少」由消费方决定。`ack` 与 `sink` 在任何花销之前
就发出去了。`done` 会等所有已提交的片，所以它能如实报告到底说了些什么。

### 线程

产生事件的是一条线程（`echoturn-reply`）：它读模型、切句子、攒片、提交合成。合成跑在一个
共享的 `ThreadPoolExecutor` 上，大小由 `ECHOTURN_TTS_POOL_SIZE` 决定，**每进程只建一次** ——
这条上限取决于供应商能容忍多少并发，而不是有多少人在同时说话。

排序是 `_AudioOrder` 里的一把锁加一个计数器。提前完成的片会在一个字典里等着，直到它前面
每一片都发出去了；`idx` 存在的全部理由就是这个：没有它，同一轮里的两句话会互相穿插。

纯文字的轮次根本不碰线程池，连 `ECHOTURN_TTS_PROVIDER` 都不会去解析 —— 纯文字轮次省下的
主要就是这一块。

### 取消

三个入口，一个含义：

* 调用方置自己的 `threading.Event`（浏览器标签页关了、客户端 abort 了一个 fetch）；
* 消费方把生成器关掉；
* 同一个 key 上更新的一轮顶掉这一轮，经由 `LiveTurns`。

三条路置的是同一个标志。它在事件之间被检查，所以 200 ms 内能被感觉到，随后流水线发出
`aborted` 并停下。已经交出去的活儿收不回来 —— 请求已经发了 —— 所以最坏情况是多付一片的
钱，递给了没人。

SSE 桥没法从自己的线程里关生成器：持有者可能正在 `next()` 里面，而关闭一个正在运行的
生成器会抛异常。它的做法是置标志然后等 —— 这就是「为什么既有标志又有生成器协议」的答案。

## 刻意不做的事

**记忆。** `echoturn.store` 只保存近期消息、设上限、静默太久就重开。它不抽取、不总结、
不检索。一个永远只被读的窗口不可能记得一百轮之前的事；想要那个的宿主自己带一套来，
流水线不会察觉。

**人设。** 系统提示是 `TurnInput` 上的一个字段。助手被告知自己是什么，属于产品，不属于
传输层。

**界面。** `clients/` 是一个浏览器客户端，`examples/` 是一个用它的页面 —— 一条听不见声音的
流水线很难被人采用。但两者都不是宿主必须照着来的形状。

## 另见

* [events.md](events.md) —— 线上契约
* [providers.md](providers.md) —— 怎么写一个适配器
* [turn-taking.md](turn-taking.md) —— 断句与打断
* [client.md](client.md) —— 浏览器客户端
* [tuning.md](tuning.md) —— 每一个阈值与它是对着什么量出来的
