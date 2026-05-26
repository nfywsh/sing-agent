"""sing-agent: 歌声克隆项目 - 通过参考音色生成具有该音色的歌曲."""

from audio_prep import prepare_audio_for_soulx, validate_audio_format
from soulx_client import convert_vocal_timbre, SoulXClient
from diffrhythm_client import generate_song_with_diffrhythm, DiffRhythmClient
from vocal_separator import separate_vocals, VocalSeparator
from orchestrator import (
    SingAgentOrchestrator,
    clone_song_with_timbre,
    PipelineState
)

__all__ = [
    # 音频预处理
    "prepare_audio_for_soulx",
    "validate_audio_format",
    # SoulX-Singer
    "convert_vocal_timbre",
    "SoulXClient",
    # DiffRhythm
    "generate_song_with_diffrhythm",
    "DiffRhythmClient",
    # 人声分离
    "separate_vocals",
    "VocalSeparator",
    # 流水线
    "SingAgentOrchestrator",
    "clone_song_with_timbre",
    "PipelineState",
]
