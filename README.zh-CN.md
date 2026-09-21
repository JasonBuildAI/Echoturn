# Echoturn

[![CI](https://github.com/JasonBuildAI/Echoturn/actions/workflows/ci.yml/badge.svg)](https://github.com/JasonBuildAI/Echoturn/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)

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
   POST /api/chat/stream ──► 系统提示词 + 上下文窗口 ──► LLM（流式）
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
python -m echoturn.cli.demo --mock          # 终端里打字，听 mock 语音
python -m examples.minimal_call.app         # 浏览器里直接跟它说话
```

## 安装

```bash
pip install echoturn            # 核心：流水线 + 供应商，不含 Web 框架
pip install "echoturn[vad]"     # 加上本地断句 / 说完判定模型
pip install "echoturn[web]"     # 加上 FastAPI 的 SSE 适配与示例页
pip install "echoturn[cli]"     # 加上 sounddevice 的麦克风 / 扬声器示例
```

核心只依赖 `httpx`；Web 框架与 ONNX 运行时刻意做成可选 —— 流水线只产出事件，
怎么送出去由宿主决定。

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
默认值是**量出来的**，不是拍出来的 —— 每一个数的来历见
[docs/tuning.md](docs/tuning.md)。

## 文档

| 文档 | 内容 |
|---|---|
| [docs/architecture.md](docs/architecture.md) | 模块、线程模型、数据流 |
| [docs/events.md](docs/events.md) | 每个事件的线上契约 |
| [docs/providers.md](docs/providers.md) | 怎么写一个 ASR / TTS / LLM 适配器 |
| [docs/turn-taking.md](docs/turn-taking.md) | 断句、插话、回声处理 |
| [docs/tuning.md](docs/tuning.md) | 每一个旋钮与它的默认值是怎么量出来的 |
| [docs/client.md](docs/client.md) | 浏览器端：采集、播放、打断 |

English README: [README.md](README.md)。

## 参与

见 [CONTRIBUTING.md](CONTRIBUTING.md)。这里有两件事比什么都重要：
护栏必须**真的会失败**，文档里的数字必须**真的量过**。

## 许可证

Apache-2.0，见 [LICENSE](LICENSE)。
