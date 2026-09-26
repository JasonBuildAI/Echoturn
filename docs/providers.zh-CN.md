# 供应商

**English: [providers.md](providers.md)** —— 英文版是唯一真源，本页是它的中文对照。
两版不一致时以英文版为准；改英文版时要同一个 commit 改这一页。

三个协议，都在 `echoturn.protocols` 里。它们刻意做成 `Protocol` 而不是基类：要求继承的话，
宿主就被迫依赖这个包，而「不被迫依赖」正是全部意义。

```python
class ASRClient:
    def transcribe(self, audio: bytes, *, sample_rate: int, fmt: str, lang: str) -> str: ...

class TTSClient:
    def synth(self, text: str, *, emotion: str | None = None, voice: str | None = None) -> bytes: ...
    def synth_stream(self, text, *, emotion=None, voice=None, chunk_cb=None) -> bytes | None: ...

class LLMClient:
    def stream(self, messages) -> Iterator[str]: ...
```

## 各自承诺了什么

### `transcribe`

`fmt` 是容器名 —— `"wav"`、`"mp3"`；`lang` 是提示，`"auto"` 表示「你自己判断」。默认值真的
就是 `auto`：写死一个错的语种比不写更糟，因为识别器会**信心十足地**转写成错误的语言，而不是
报告自己不确定。

**空字符串是合法答案。** 它的意思是「没东西可听」，这不是失败，更不能当成失败抛出来。
`clients/call.js` 为它留了整整一条路径。

`audio` 是 bytes 而不是解析好的对象，所以已经把音频解码过的宿主不必为了被接受而再包一层。

### `synth` 与 `synth_stream`

`synth` 返回一整片。`synth_stream` 每完成一小段就交给 `chunk_cb`；给了回调时它返回 `None` ——
音频已经交出去了。

流式是「一句话还没说完就能出声」的前提，所以供应商支持的话就值得实现。不能流式的供应商只实现
`synth`，再混入 `echoturn.providers.base.WholeClipTTS`，由它把一种适配成另一种：

```python
from echoturn.providers.base import WholeClipTTS

class MyVoice(WholeClipTTS):
    provider = "mine"

    def synth(self, text, *, emotion=None, voice=None) -> bytes:
        return b"..."          # 一整片 WAV
```

`emotion` 是可选的标签。没有情绪控制的供应商忽略它，而不是拒绝 —— 流水线把它传给想要的人，
并且对「谁想要」没有意见。

### `stream`

产出的是**文本片段**，不是 token，也不是一个最终的响应对象。一个片段可能在某句话中间就断了，
也可能带着标点 —— 所以判断句子边界的那一层是调用方，也就是 `echoturn.text`。

只能一次性回答的供应商就产出一个片段。下游什么都不用改，只是首声来得晚一些。

## 自带的适配器

| 名字 | 是什么 | 额外依赖 |
|---|---|---|
| `mock` | 离线：一声蜂鸣、一句占位转写、一次回声 | 无 |
| `openai` | 任何提供 OpenAI HTTP 形状的服务 | 无（用 `httpx`） |

`openai` 指的是协议，不是那家公司。让它指向别家的是 `ECHOTURN_BASE_URL`：任何路由相同、
请求体相同的端点都能用。

```bash
export ECHOTURN_LLM_PROVIDER=openai
export ECHOTURN_LLM_MODEL=gpt-4o-mini
export OPENAI_API_KEY=...
python -m echoturn.cli.demo --no-play
```

## 注册一个

加进注册表，然后按名字选它：

```python
from echoturn.providers.registry import LLM_PROVIDERS

LLM_PROVIDERS["mine"] = MyModel
```

```bash
export ECHOTURN_LLM_PROVIDER=mine
```

或者直接传进去，测试就是这么干的：

```python
run_turn(turn, TurnDeps(llm=MyModel(), tts=MyVoice()))
```

## 名字不存在时会怎样

`make_llm("gpt4")` 会抛异常，消息里带上可用的名字：

```text
unknown LLM provider 'gpt4' (set ECHOTURN_LLM_PROVIDER, or pass the name directly); available: mock, openai
```

改成回落到 mock 会把配置文件里的一个错字变成「看起来能用、用蜂鸣音说话、永远不会去联系
它本该联系的那个供应商」的系统。只有在什么都没要求的时候，默认值才是 mock。

## 超时与连接池

每个 HTTP 请求带自己的超时，因为一个统一默认值必须同时做到「对识别足够短」和「对合成足够
长」，结果必然对其中一个不合适。

| 设置 | 默认值 | 用在哪 |
|---|---|---|
| `ECHOTURN_LLM_TIMEOUT` | `60.0` | 一次模型调用 |
| `ECHOTURN_TTS_TIMEOUT` | `120.0` | 一次合成请求 |
| `ECHOTURN_ASR_TIMEOUT` | `60.0` | 一次识别 |
| `ECHOTURN_HTTP_POOL_SIZE` | `32` | 进程级保持的连接数 |
| `ECHOTURN_HTTP_KEEPALIVE_EXPIRY` | `60.0` | 空闲连接保持多久 |

最后一条不是请求超时，而是一条连接在池子里**空闲**多久才被丢掉。httpx 自己的默认是 5 秒，
比一场对话里的安静间隔要短 —— 一条回复要先被生成、播出来、再被听完，下一个请求才发出去 ——
所以 5 秒意味着那个请求要在关键路径上重新做一次 TCP + TLS 握手，而这正是共享客户端存在的
理由。60 秒覆盖一场通话真实会有的间隔；如果你的网络环境不能接受把 socket 留这么久，就把它
调小。

## 失败

供应商失败就抛。流水线在出错的那一片上接住它然后继续：一次合成失败会在 `done` 上留下一条
带片号的 `warning`，那句话的文本仍然在 `reply` 里。模型调用失败则是 `error` 事件，因为
已经没有回复可以继续了。

`error` 事件上的消息已经过 `safe_message`，它会剥掉 URL、密钥和内部路径。原文进宿主的日志。

## 离线供应商

`MockTTS` 是一声蜂鸣，长度跟着文本走，音高跟着情绪标签走。`MockASR` 如实报告自己收到了
什么，而不去编词 —— `[mock transcript of 1.4s of wav]`。`MockLLM` 把提示词切成小片回放。

它们被做成**一眼假**，这才是最要紧的性质。一个像模像样的替身，会被人不小心发上线，然后
花一天去查。

它们同时是逐字节可复现的 —— 正是这一点让「事件流没有变」这类断言成为可能。
