"""歌声克隆完整流水线 Orchestrator."""

import os
import logging
import subprocess
import json
from enum import Enum
from typing import Optional, Dict, Any, List
from pathlib import Path

from audio_prep import prepare_audio_for_soulx
from soulx_client import convert_vocal_timbre, SoulXClient
from diffrhythm_client import generate_song_with_diffrhythm, DiffRhythmClient
from ace_step_client import generate_song_with_acestep, ACEStepClient
from vocal_separator import separate_vocals, VocalSeparator
from voice_designer import VoiceDesigner
from lyrics_generator import LyricsGenerator

logger = logging.getLogger(__name__)


class ModelType(Enum):
    """支持的生成模型枚举."""
    DIFFRHYTHM = "diffrhythm"
    ACE_STEP = "acestep"


class PipelineState(Enum):
    """流水线状态枚举."""
    IDLE = "idle"
    VOICE_DESIGN = "voice_design"      # 音色设计中
    LYRICS_GENERATING = "lyrics_gen"   # 歌词生成中
    PREGENERATING = "pregenerating"    # 预生成中
    GENERATING = "generating"          # 实时生成中
    SEPARATING = "separating"          # 人声分离中
    CONVERTING = "converting"          # 音色转换中
    COMPLETED = "completed"
    FAILED = "failed"


class SingAgentOrchestrator:
    """歌声克隆流水线 Orchestrator."""

    def __init__(
        self,
        output_dir: str = "/data/voice-temp/output",
        pregenerated_dir: str = "/data/voice-temp/songs",
        use_pregenerated: bool = True,
        model_type: ModelType = ModelType.ACE_STEP
    ):
        """
        初始化 Orchestrator.

        Args:
            output_dir: 最终输出目录
            pregenerated_dir: 预生成歌曲存储目录
            use_pregenerated: 是否使用预生成模式 (默认 True)
            model_type: 歌曲生成模型 (默认 ACE-Step)
        """
        self.output_dir = output_dir
        self.pregenerated_dir = pregenerated_dir
        self.use_pregenerated = use_pregenerated
        self.model_type = model_type

        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(pregenerated_dir, exist_ok=True)

        self.state = PipelineState.IDLE
        self.last_error: Optional[str] = None

        # 初始化客户端
        self._soulx_client = SoulXClient()
        self._diff_client = DiffRhythmClient()
        self._ace_client = ACEStepClient()
        self._separator = VocalSeparator()
        self._voice_designer = VoiceDesigner()
        self._lyrics_generator = LyricsGenerator()

        # 缓存上次使用的音色路径 (用于音色复用判断)
        self._last_voice_path: Optional[str] = None

    def pregenerate_song(
        self,
        song_id: str,
        lyrics: str,
        style: str = "Pop, Happy",
        duration: int = 90,
        ref_audio: str = None,
        model_type: ModelType = None
    ) -> Dict[str, str]:
        """
        预生成歌曲 (DiffRhythm 或 ACE-Step + 人声分离).

        Args:
            song_id: 歌曲唯一标识
            lyrics: 歌词
            style: 风格提示词
            duration: 目标时长 (秒)
            ref_audio: 参考音频路径 (用于提供人声参考，DiffRhythm 专用)
            model_type: 生成模型类型（默认为 self.model_type）

        Returns:
            包含 song_path, vocal_path, metadata_path 的字典
        """
        self.state = PipelineState.PREGENERATING
        song_dir = os.path.join(self.pregenerated_dir, song_id)
        os.makedirs(song_dir, exist_ok=True)

        if model_type is None:
            model_type = self.model_type

        try:
            # 1. 根据模型类型生成歌曲
            self.state = PipelineState.GENERATING
            if model_type == ModelType.DIFFRHYTHM:
                logger.info(f"Generating song with DiffRhythm: {song_id}")
                song_path = generate_song_with_diffrhythm(
                    lyrics=lyrics,
                    song_name=song_id,
                    style=style,
                    duration=duration,
                    ref_audio=ref_audio
                )
            else:  # ACE_STEP
                logger.info(f"Generating song with ACE-Step: {song_id}")
                song_path = generate_song_with_acestep(
                    lyrics=lyrics,
                    song_name=song_id,
                    caption="",  # 不重写歌词
                    duration=duration
                )

            # 复制到存储目录
            final_song_path = os.path.join(song_dir, "song.wav")
            subprocess.run(["cp", song_path, final_song_path], check=True)

            # 2. 人声分离
            self.state = PipelineState.SEPARATING
            logger.info(f"Separating vocals: {song_id}")
            vocal_path = separate_vocals(final_song_path, output_dir=song_dir)

            # 重命名为标准路径
            final_vocal_path = os.path.join(song_dir, "vocal.wav")
            subprocess.run(["mv", vocal_path, final_vocal_path], check=True)
            vocal_path = final_vocal_path

            # 3. 保存元数据
            import json
            metadata = {
                "song_id": song_id,
                "lyrics": lyrics,
                "style": style,
                "duration": duration,
                "song_path": final_song_path,
                "vocal_path": final_vocal_path,
                "status": "ready"
            }
            metadata_path = os.path.join(song_dir, "metadata.json")
            with open(metadata_path, "w") as f:
                json.dump(metadata, f, indent=2)

            self.state = PipelineState.COMPLETED
            logger.info(f"Pre-generation complete: {song_id}")

            return {
                "song_id": song_id,
                "song_path": final_song_path,
                "vocal_path": vocal_path,
                "metadata_path": metadata_path
            }

        except Exception as e:
            self.state = PipelineState.FAILED
            self.last_error = str(e)
            logger.error(f"Pre-generation failed: {e}")
            raise

    def realtime_convert(
        self,
        prompt_audio: str,
        target_vocal_path: str,
        pitch_shift: int = 0,
        n_step: int = 32,
        cfg: float = 1.0
    ) -> str:
        """
        实时音色转换 (SoulX-Singer).

        Args:
            prompt_audio: 参考音色音频 (24kHz mono, native for SoulX-Singer)
            target_vocal_path: 目标人声路径
            pitch_shift: 音高偏移
            n_step: 采样步数
            cfg: cfg系数，低值减少失真

        Returns:
            转换后的音频路径
        """
        self.state = PipelineState.CONVERTING

        try:
            # 预处理音频 (确保 24kHz mono，原生采样率)
            prompt_prepared = prepare_audio_for_soulx(prompt_audio)
            target_prepared = prepare_audio_for_soulx(target_vocal_path)

            # 调用 SoulX-Singer
            logger.info("Converting timbre with SoulX-Singer...")
            result = convert_vocal_timbre(
                prompt_audio=prompt_prepared,
                target_audio=target_prepared,
                pitch_shift=pitch_shift,
                n_step=n_step,
                cfg=cfg
            )

            # 复制到输出目录
            output_path = os.path.join(self.output_dir, f"converted_{os.getpid()}.wav")
            subprocess.run(["cp", result, output_path], check=True)

            self.state = PipelineState.COMPLETED
            logger.info(f"Timbre conversion complete: {output_path}")
            return output_path

        except Exception as e:
            self.state = PipelineState.FAILED
            self.last_error = str(e)
            logger.error(f"Timbre conversion failed: {e}")
            raise

    def full_pipeline(
        self,
        voice_path: Optional[str] = None,
        voice_instructions: str = "清澈甜美的女声",
        lyrics: Optional[str] = None,
        theme: Optional[str] = None,
        style: str = "Pop, Happy",
        duration: int = 90,
        pitch_shift: int = 0,
        ref_audio: str = None
    ) -> str:
        """
        完整流水线（新版，支持音色设计和歌词生成）

        1. 如果没有提供 voice_path，使用 Qwen3-TTS-VoiceDesign 生成
        2. 如果没有提供 lyrics，使用 Qwen3.6-35B 生成
        3. DiffRhythm -> 分离 -> SoulX-Singer

        Args:
            voice_path: 用户提供的音色文件路径
            voice_instructions: 音色描述（当 voice_path 为 None 时使用）
            lyrics: 歌词（如果为 None，则使用 LLM 生成）
            theme: 歌词主题（当 lyrics 为 None 时使用）
            style: 风格
            duration: 时长
            pitch_shift: 音高偏移
            ref_audio: 参考音频路径（已废弃，推荐使用 voice_path）

        Returns:
            最终转换后的音频路径
        """
        self.state = PipelineState.GENERATING

        try:
            # Step 1: 音色处理
            voice_result = self.design_or_use_voice(voice_path, voice_instructions)
            prompt_audio = voice_result["host_path"]

            # Step 2: 歌词处理
            if lyrics is None:
                lyrics_result = self.generate_lyrics(theme=theme)
                lyrics = lyrics_result["lyrics"]

            # Step 3: DiffRhythm 生成歌曲
            logger.info("Step 3: Generating song with DiffRhythm...")
            song_path = generate_song_with_diffrhythm(
                lyrics=lyrics,
                song_name=f"temp_{os.getpid()}",
                style=style,
                duration=duration,
                ref_audio=voice_result["container_path"]  # 使用容器内路径
            )

            # Step 4: 人声分离
            self.state = PipelineState.SEPARATING
            logger.info("Step 4: Separating vocals...")
            vocal_path = separate_vocals(song_path)

            # Step 5: 音色转换
            self.state = PipelineState.CONVERTING
            logger.info("Step 5: Converting timbre...")
            result = self.realtime_convert(
                prompt_audio=prompt_audio,
                target_vocal_path=vocal_path,
                pitch_shift=pitch_shift
            )

            self.state = PipelineState.COMPLETED
            return result

        except Exception as e:
            self.state = PipelineState.FAILED
            self.last_error = str(e)
            logger.error(f"Full pipeline failed: {e}")
            raise

    def get_state(self) -> PipelineState:
        """获取当前状态."""
        return self.state

    def get_last_error(self) -> Optional[str]:
        """获取最后错误信息."""
        return self.last_error

    # ========== 新增：音色和歌词生成流程 ==========

    def design_or_use_voice(self, voice_path: Optional[str] = None, voice_instructions: str = "清澈甜美的女声") -> Dict[str, str]:
        """设计音色或使用已存在的音色文件

        Args:
            voice_path: 用户提供的音色文件路径，如果为 None 则使用 Qwen3-TTS-VoiceDesign 生成
            voice_instructions: 音色描述（当 voice_path 为 None 时使用）

        Returns:
            包含 host_path 和 container_path 的字典
        """
        self.state = PipelineState.VOICE_DESIGN

        try:
            # 如果用户提供了音色文件
            if voice_path is not None:
                logger.info(f"Using existing voice file: {voice_path}")
                result = self._voice_designer.use_existing_voice(voice_path)
            else:
                # 检查是否可以复用之前的音色
                if (self._last_voice_path is not None and
                    voice_instructions == getattr(self, '_last_voice_instructions', None)):
                    logger.info(f"Reusing previous voice: {self._last_voice_path}")
                    result = self._voice_designer.use_existing_voice(self._last_voice_path)
                else:
                    # 生成新音色
                    logger.info(f"Designing new voice with instructions: {voice_instructions}")
                    result = self._voice_designer.design_voice(voice_instructions)
                    self._last_voice_path = result["host_path"]
                    self._last_voice_instructions = voice_instructions

            self.state = PipelineState.COMPLETED
            return result

        except Exception as e:
            self.state = PipelineState.FAILED
            self.last_error = str(e)
            logger.error(f"Voice design failed: {e}")
            raise

    def generate_lyrics(self, theme: Optional[str] = None, save: bool = True) -> Dict[str, str]:
        """使用 Qwen3.6-35B 生成歌词

        Args:
            theme: 歌词主题或风格描述
            save: 是否保存到文件

        Returns:
            包含 lyrics 和 file_path (如果 save=True) 的字典
        """
        self.state = PipelineState.LYRICS_GENERATING

        try:
            logger.info(f"Generating lyrics with theme: {theme}")

            if save:
                result = self._lyrics_generator.generate_and_save(theme=theme)
            else:
                lyrics = self._lyrics_generator.generate_lyrics(theme=theme)
                result = {"lyrics": lyrics, "file_path": None, "container_path": None}

            self.state = PipelineState.COMPLETED
            return result

        except Exception as e:
            self.state = PipelineState.FAILED
            self.last_error = str(e)
            logger.error(f"Lyrics generation failed: {e}")
            raise

    def full_workflow(
        self,
        voice_path: Optional[str] = None,
        voice_instructions: str = "清澈甜美的女声",
        theme: Optional[str] = None,
        style: str = "Pop, Happy",
        duration: int = 90,
        model_type: ModelType = None
    ) -> Dict[str, Any]:
        """完整业务流程

        1. 音色处理（用户传入 vs Qwen3-TTS-VoiceDesign）
        2. 歌词生成（Qwen3.6-35B）
        3. 生成歌曲（DiffRhythm 或 ACE-Step）
        4. 人声分离
        5. SoulX-Singer 音色转换（如提供音色）

        Args:
            voice_path: 用户提供的音色文件路径
            voice_instructions: 音色描述（当 voice_path 为 None 时使用）
            theme: 歌词主题
            style: 风格提示词
            duration: 目标时长
            model_type: 生成模型类型（默认为 self.model_type）

        Returns:
            包含 song_id, song_path, vocal_path, converted_path 等的字典
        """
        if model_type is None:
            model_type = self.model_type

        try:
            # Step 1: 音色处理
            voice_result = self.design_or_use_voice(voice_path, voice_instructions)
            logger.info(f"Voice ready: {voice_result['host_path']}")

            # Step 2: 歌词生成
            lyrics_result = self.generate_lyrics(theme=theme)
            logger.info(f"Lyrics ready: {lyrics_result['file_path']}")

            # Step 3: 生成歌曲
            song_id = f"song_{os.getpid()}"
            song_dir = os.path.join(self.pregenerated_dir, song_id)
            os.makedirs(song_dir, exist_ok=True)

            self.state = PipelineState.PREGENERATING

            if model_type == ModelType.DIFFRHYTHM:
                # DiffRhythm 需要 ref_audio 来控制人声特征
                logger.info("Step 3: Generating song with DiffRhythm...")
                song_path = generate_song_with_diffrhythm(
                    lyrics=lyrics_result["lyrics"],
                    song_name=song_id,
                    style=style,
                    duration=duration,
                    ref_audio=voice_result["host_path"]  # 传入宿主机路径
                )
            else:
                # ACE-Step 不支持音频参考音色
                logger.info("Step 3: Generating song with ACE-Step...")
                song_path = generate_song_with_acestep(
                    lyrics=lyrics_result["lyrics"],
                    song_name=song_id,
                    caption="",  # 不重写歌词
                    duration=duration
                )

            # 复制到存储目录
            final_song_path = os.path.join(song_dir, "song.wav")
            subprocess.run(["cp", song_path, final_song_path], check=True)

            # Step 4: 人声分离
            self.state = PipelineState.SEPARATING
            logger.info("Step 4: Separating vocals...")
            vocal_path = separate_vocals(final_song_path, output_dir=song_dir)
            final_vocal_path = os.path.join(song_dir, "vocal.wav")
            subprocess.run(["mv", vocal_path, final_vocal_path], check=True)
            vocal_path = final_vocal_path

            # Step 5: 保存元数据
            metadata = {
                "song_id": song_id,
                "lyrics": lyrics_result["lyrics"],
                "voice_path": voice_result["host_path"],
                "voice_container_path": voice_result["container_path"],
                "style": style,
                "duration": duration,
                "model_type": model_type.value,
                "song_path": final_song_path,
                "vocal_path": vocal_path,
                "status": "ready"
            }
            metadata_path = os.path.join(song_dir, "metadata.json")
            with open(metadata_path, "w") as f:
                json.dump(metadata, f, indent=2)

            self.state = PipelineState.COMPLETED
            logger.info(f"Full workflow complete: {song_id}")

            return {
                "song_id": song_id,
                "song_path": final_song_path,
                "vocal_path": vocal_path,
                "metadata_path": metadata_path,
                "voice_path": voice_result["host_path"],
                "lyrics": lyrics_result["lyrics"]
            }

        except Exception as e:
            self.state = PipelineState.FAILED
            self.last_error = str(e)
            logger.error(f"Full workflow failed: {e}")
            raise


# 便捷函数
def clone_song_with_timbre(
    voice_path: Optional[str] = None,
    voice_instructions: str = "清澈甜美的女声",
    lyrics: Optional[str] = None,
    theme: Optional[str] = None,
    style: str = "Pop, Happy",
    duration: int = 90,
    pitch_shift: int = 0
) -> str:
    """
    便捷函数: 通过参考音色克隆歌曲（支持音色设计和歌词生成）

    Args:
        voice_path: 用户提供的音色文件路径（可选）
        voice_instructions: 音色描述（当 voice_path 为 None 时使用）
        lyrics: 歌词（可选，如果为 None 则使用 LLM 生成）
        theme: 歌词主题（当 lyrics 为 None 时使用）
        style: 风格提示词
        duration: 目标时长
        pitch_shift: 音高偏移

    Returns:
        转换后的音频路径
    """
    orchestrator = SingAgentOrchestrator()
    return orchestrator.full_pipeline(
        voice_path=voice_path,
        voice_instructions=voice_instructions,
        lyrics=lyrics,
        theme=theme,
        style=style,
        duration=duration,
        pitch_shift=pitch_shift
    )
