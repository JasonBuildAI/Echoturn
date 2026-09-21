"""Echoturn: a provider-agnostic realtime voice conversation pipeline.

The package is deliberately split so that the transport, the provider SDKs and
the audio toolchain can be replaced independently:

* ``echoturn.text``    - turning model output into something worth saying out loud
* ``echoturn.audio``   - PCM/WAV plumbing and voice consistency helpers
* ``echoturn.vad``     - "is this speech, and how much of it" (optional extra)
* ``echoturn.endpoint``- "has this person finished their sentence" (optional extra)
* ``echoturn.providers``- ASR/TTS/LLM adapters, including offline mocks
* ``echoturn.pipeline`` - one turn, from text to ordered audio chunks
* ``echoturn.server``  - transcript window, session bookkeeping, SSE encoding

Nothing in the core imports a web framework: the pipeline yields plain events
and the host decides how to ship them.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
