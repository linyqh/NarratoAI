"""Deterministic guardrails for claims derived only from visual evidence."""

from __future__ import annotations


_AUDIO_CLAIM_TERMS = (
    "对白",
    "台词",
    "声音",
    "声响",
    "音效",
    "环境音",
    "原声",
    "音乐",
    "配乐",
    "旁白",
    "语音",
    "歌声",
    "爆炸声",
    "枪声",
    "铃声",
    "雷声",
    "风声",
    "水声",
    "引擎声",
    "脚步声",
    "喊声",
    "哭声",
    "笑声",
    "说出",
    "喊出",
    "听到",
    "听见",
    "画外",
    "dialogue",
    "voice-over",
    "voiceover",
    "music",
    "soundtrack",
    "sound effect",
    "audio",
    "off-screen",
)


def contains_unsupported_audio_claim(reason: str) -> bool:
    """Return True when a visual-only reason asserts an audible/off-screen fact."""
    normalized = str(reason or "").strip().lower()
    return any(term in normalized for term in _AUDIO_CLAIM_TERMS)
