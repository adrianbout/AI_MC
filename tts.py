"""
Turn one MC phrase into a WAV file with the Azure realtime voices.

The realtime model is asked to read the text verbatim; always preview the
result in the admin panel before the show, and regenerate if it improvised.

Run directly to test:  python tts.py "أهلاً وسهلاً بكم" ash natural
"""

import asyncio
import base64
import os
import sys
import wave

from openai import AsyncOpenAI

import config

READER = ("You are a voice-over reader for a live award ceremony, speaking "
          "Modern Standard Arabic (Fusha) unless the text is in another language. "
          "Read the given text exactly, word for word. Do not add, drop, translate "
          "or comment on anything. ")


def client() -> AsyncOpenAI:
    if not (config.ENDPOINT and config.API_KEY):
        raise RuntimeError("Azure endpoint/key missing - set them in .env")
    return AsyncOpenAI(api_key=config.API_KEY, base_url=config.HTTP_BASE,
                       websocket_base_url=config.WS_BASE,
                       default_headers={"api-key": config.API_KEY})


async def synthesize(text: str, voice: str, style: str,
                     speed: float = config.VOICE_SPEED) -> bytes:
    """Return raw PCM16 mono @ 24 kHz for the text."""
    if voice not in config.VOICES:
        raise ValueError(f"unknown voice {voice!r}")
    pcm = bytearray()
    async with client().realtime.connect(model=config.DEPLOYMENT) as conn:
        await conn.session.update(session={
            "type": "realtime",
            "instructions": READER + config.VOICE_STYLES.get(style, ""),
            "output_modalities": ["audio"],
            "audio": {"output": {"format": {"type": "audio/pcm", "rate": config.SAMPLE_RATE},
                                 "voice": voice, "speed": max(0.25, min(1.5, speed))}},
        })
        await conn.response.create(response={"instructions": f"Say exactly:\n{text}"})
        async for event in conn:
            if event.type == "response.output_audio.delta":
                pcm += base64.b64decode(event.delta)
            elif event.type == "response.done":
                break
            elif event.type == "error":
                raise RuntimeError(event.error)
    if not pcm:
        raise RuntimeError("no audio returned")
    return bytes(pcm)


def write_wav(pcm: bytes, path: str) -> float:
    """Save PCM16 as WAV; returns the duration in seconds."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(config.SAMPLE_RATE)
        w.writeframes(pcm)
    return len(pcm) / 2 / config.SAMPLE_RATE


def generate(text: str, voice: str, style: str, path: str,
             speed: float = config.VOICE_SPEED) -> float:
    """Blocking helper for the web server: synthesize and save, return seconds."""
    try:
        pcm = asyncio.run(synthesize(text, voice, style, speed))
    except TimeoutError:   # a slow websocket handshake; one retry usually gets through
        pcm = asyncio.run(synthesize(text, voice, style, speed))
    return write_wav(pcm, path)


if __name__ == "__main__":
    phrase = sys.argv[1] if len(sys.argv) > 1 else "أهلاً وسهلاً بكم في الحفل."
    voice = sys.argv[2] if len(sys.argv) > 2 else "ash"
    style = sys.argv[3] if len(sys.argv) > 3 else "natural"
    out = os.path.join(config.AUDIO_DIR, "test.wav")
    print(f"{generate(phrase, voice, style, out):.1f}s -> {out}")
