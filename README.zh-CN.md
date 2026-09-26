# Echoturn

[![CI](https://github.com/JasonBuildAI/Echoturn/actions/workflows/ci.yml/badge.svg)](https://github.com/JasonBuildAI/Echoturn/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)

**简体中文** · [English](README.md)

**一条与供应商无关的实时语音对话流水线。**

一个语音助手「像个人在跟你说话」还是「像对讲机」，差别几乎都落在几件又烦又难的小事上。
Echoturn 把这部分单独抽出来做成一个小库，你继续用自己的 ASR / LLM / TTS：

* **知道对方说完了没有。** 只看静音永远分不清「一句话说完了」和「句中喘了口气」；
  Echoturn 量两件事：**真正的人声有多长**、**这句说完了吗**，只有在两个模型都用不上时
  才回落到静音阈值。
* **不挡着人说话。** 她还在想、或者在收尾那半句时你开口，你说的那句**不会被丢掉** ——
  它被留下来当作下一轮的开头。
* **开口就出声。** 文本一产出一小段就送去合成，首声不等整段答案。
* **音频绝不乱序。** 合成天然乱序完成，播放严格按片序号，一个字不跳、不叠。

以上全部与供应商无关，并且可以用 mock 供应商**完全离线**跑通。

> **状态：早期。** 流水线、供应商、断句与 demo 可用，公开接口仍在收敛中。
> 变更见 [CHANGELOG.md](CHANGELOG.md)。

## Echoturn 的优势

| 优势 | 落到实处的意思 |
|---|---|
| **核心只有一个依赖** | `pip install echoturn` 之后整份代码都能读完：没有 Web 框架、没有运行时、不要账号、没有埋点。Web、ONNX、设备那几块都是你自己决定要不要装的额外件。 |
| **契约小到可以照搬** | 七个事件就是全部公开面，所以**传输是你的事**。浏览器 demo 与终端 demo 只是同一个生成器的两个宿主。 |
| **记忆与人设层还是你的** | Echoturn 什么都不记，也不决定「给模型看什么」：它交给你一轮，prompt 由你组装。 |
| **断句敢承认自己在猜** | 「这句说完了吗」是量出来的 —— 真正的人声有多长 + 一个端点模型 —— 只有在不得不时才回落到静音截止时间；模型不在会明说，不会悄悄咽掉。 |
| **插话不吞掉用户的话** | 她还在合成时你开口，你说的那句会成为下一轮的开头；播放还会对照她自己的回声做门控。 |
| **音频不可能乱序** | 合成天然乱序完成，播放严格按片序号排序，不跳、不叠、不交叉。 |
| **首声不等最后一个 token** | 模型还在写，文本就一小段一小段送去合成。`bench/latency.py --compare` 会告诉你它在哪里赢 —— 也会告诉你它在哪里输。 |
| **从构造上就能离线** | mock 的 ASR / LLM / TTS 能把整条流水线跑完，不要 Key、不联网、不下模型；CI 在 Python 3.10–3.12 上跑，不带任何密钥。 |

这件事的另一半也写下来了：更大那几家强在哪、托管式端到端音频会话的成本结构长什么样、
以及哪些情况下你该用它们而不是这个 —— 全部在 [docs/positioning.zh-CN.md](docs/positioning.zh-CN.md)。

## 一轮是怎么流的

```
 麦克风 ──► 采集（AudioWorklet）──► 本地静音游标 ──┐
                                                  │
        ┌──────────────「这句说完了吗」────────────┘
        │
        ▼
   POST /api/transcribe ──► ASR ──► 文本
                                     │
                                     ▼
   POST /api/turn ──► 系统提示词 + 上下文窗口 ──► LLM（流式）
                                     │
                                     ├──► sentence 事件 ──► 字幕
                                     │
                                     └──► 攒句 ──► TTS ──► audio 事件（带片序号）
                                                                  │
                                                                  ▼
                                              有序播放（WebAudio 队列，接缝为零）
```

文字输入跳过采集与 ASR，在提示词那一步接进**同一条**流水线：一轮只有一条代码路径，
不存在第二套分支。

## 快速开始

不需要任何 Key、不联网、不下模型：

```bash
pip install -e ".[web]"
echoturn-demo --mock                        # 终端里打字，听蜂鸣音
echoturn-demo --mock --mic                  # 改成说话（要装 echoturn[cli]）
python examples/minimal_call/app.py         # 浏览器里打字跟它说话（mock 供应商）
```

`echoturn-demo` 是随包安装的命令行入口；`python -m echoturn.cli.demo` 是同一个程序，
不想依赖 `PATH` 时用后者。打字模式下回车发送；`--mic` 下第一次回车开始录音，
再按一次回车把刚才说的发出去。

## 安装

```bash
pip install echoturn            # 核心：流水线 + 供应商，不含 Web 框架
pip install "echoturn[dsp]"     # 加上音高与语速处理（numpy）
pip install "echoturn[vad]"     # 加上本地断句 / 说完判定模型
pip install "echoturn[web]"     # 加上 FastAPI 的 SSE 适配与示例页
pip install "echoturn[cli]"     # 加上 sounddevice 的麦克风 / 扬声器示例
```

核心只依赖 `httpx`；Web 框架与 ONNX 运行时刻意做成可选 —— 流水线只产出事件，
怎么送出去由宿主决定。

`echoturn[vad]` 背后那两个 ONNX 模型不进 wheel（几十兆）。在你让设置去找它们的
位置装一次就够：

```bash
echoturn-fetch-models           # 缺什么下什么（等价：python scripts/fetch_models.py）
echoturn-fetch-models --check   # 把已装上的加载起来跑一次
```

除此之外没有东西需要它们。文件不在时，一轮结束只能靠静音截止时间，
`build_vad` 与 `build_turn` 都会在返回值里**明说**这一点，而不是悄悄降级。

## 配置

所有设置都是环境变量，**用的时候才读**（不是导入时读一次），所以常驻进程改了配置
不用重启。断句 / 打断的那些阈值集中在 `echoturn.config.DIALS` 一张表里，
每个数字是对着什么量出来的，见 [docs/tuning.md](docs/tuning.md)。
所有变量的名字与默认值都列在 [.env.example](.env.example) 里；它和代码里的一致，
两边一旦漂移会有测试变红。

| 环境变量 | 默认值 | 作用 |
|---|---|---|
| `ECHOTURN_LLM_PROVIDER` | `mock` | `mock`，或 `openai`（任何提供 OpenAI HTTP 形状的服务） |
| `ECHOTURN_TTS_PROVIDER` | `mock` | 同上，语音合成 |
| `ECHOTURN_ASR_PROVIDER` | `mock` | 同上，语音识别 |
| `OPENAI_API_KEY` | — | `openai` 那三个供应商的令牌 |
| `ECHOTURN_BASE_URL` | `https://api.openai.com/v1` | `openai` 供应商的接口根地址 |
| `ECHOTURN_LLM_MODEL` / `ECHOTURN_TTS_MODEL` / `ECHOTURN_ASR_MODEL` | `gpt-4o-mini` / `tts-1` / `whisper-1` | 模型名 |
| `ECHOTURN_TTS_VOICE` | `alloy` | 音色名 |
| `ECHOTURN_MODEL_DIR` | `models` | 可选 ONNX 模型放在哪 |
| `ECHOTURN_HTTP_POOL_SIZE` | `32` | 保持的连接数 |
| `ECHOTURN_HTTP_KEEPALIVE_EXPIRY` | `60.0` | 空闲连接保持多少秒 |
| `ECHOTURN_VAD_ENGINE` | `silero` | `silero`（模型）或 `energy`（只看音量） |
| `ECHOTURN_IDLE_SPLIT_SEC` | `600` | 静默超过这么久就重开上下文 |

## 接口

```python
class ASRClient:
    def transcribe(self, audio: bytes, *, sample_rate: int, fmt: str, lang: str) -> str: ...

class TTSClient:
    def synth(self, text: str, *, emotion: str | None, voice: str | None) -> bytes: ...
    def synth_stream(self, text, *, emotion=None, voice=None, chunk_cb=None): ...

class LLMClient:
    def stream(self, messages: list[dict]) -> Iterator[str]: ...
```

`run_turn` 产出的事件（每条一个 dict，可直接编成 SSE）：

| 事件 | 含义 |
|---|---|
| `ack` | 用户这条消息已落定，带它的 id |
| `sentence` | 一句可朗读的话，给打字机字幕用 |
| `audio` | 一片 base64 WAV + 片序号 + 第几条消息 |
| `sink` | 声音该从哪里出来（浏览器 / 设备 / …） |
| `aborted` | 这一轮被顶掉或取消 |
| `done` | 完整回复 + 本轮时序 |
| `error` | 这一轮失败；文案可直接给用户看 |

## 调参

所有阈值只有一张表（`echoturn.config.DIALS`），在调用时现读环境变量。
这些默认值是从一条**已经在跑的**流水线上搬过来的，不是坐在键盘前拍出来的；
每一个数是和什么对账出来的见 [docs/tuning.zh-CN.md](docs/tuning.zh-CN.md) ——
其中那个**只是起点、不是实测值**的门限，在定义它的地方
[docs/turn-taking.zh-CN.md](docs/turn-taking.zh-CN.md) 已经写明。

其中攒句阈值背后压着一个取舍，怎么在你自己的机器上把它量出来：
[docs/benchmarks.md](docs/benchmarks.md)，`python bench/latency.py --compare`。

## 文档

| 文档 | 内容 |
|---|---|
| [docs/README.zh-CN.md](docs/README.zh-CN.md) | 索引：读什么，按什么顺序读 |
| [docs/positioning.zh-CN.md](docs/positioning.zh-CN.md) | Echoturn 强在哪、不做什么，以及什么时候该用更大那一套 |
| [docs/architecture.zh-CN.md](docs/architecture.zh-CN.md) | 模块、线程模型、数据流 |
| [docs/events.zh-CN.md](docs/events.zh-CN.md) | 每个事件的线上契约 |
| [docs/providers.zh-CN.md](docs/providers.zh-CN.md) | 怎么写一个 ASR / TTS / LLM 适配器 |
| [docs/turn-taking.zh-CN.md](docs/turn-taking.zh-CN.md) | 断句、插话、回声处理 |
| [docs/tuning.zh-CN.md](docs/tuning.zh-CN.md) | 每一个旋钮与它的默认值是怎么量出来的 |
| [docs/client.zh-CN.md](docs/client.zh-CN.md) | 浏览器端：采集、播放、打断 |
| [docs/benchmarks.zh-CN.md](docs/benchmarks.zh-CN.md) | 延迟报告量的是什么，怎么读 |

每一份都有对应的英文版，**英文版是唯一真源**；两版不一致时以英文版为准。

中文版这一份是英文 [README.md](README.md) 的对照，两版在同一次改动里一起改。

## 参与

见 [CONTRIBUTING.md](CONTRIBUTING.md)。这里有两件事比什么都重要：
护栏必须**真的会失败**，文档里的数字必须**真的量过**。

## 许可证

Apache-2.0，见 [LICENSE](LICENSE)。
