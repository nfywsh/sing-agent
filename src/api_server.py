"""
歌声合成 API Server

提供 REST API 接口，支持音色设计和歌词生成
"""

import os
import logging
from typing import Optional
from pathlib import Path

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
import uvicorn

from orchestrator import SingAgentOrchestrator, ModelType

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 统一文件存储路径 (跨容器共享)
SHARED_TEMP_DIR = "/data/voice-temp"
os.makedirs(SHARED_TEMP_DIR, exist_ok=True)
os.makedirs(f"{SHARED_TEMP_DIR}/voices", exist_ok=True)
os.makedirs(f"{SHARED_TEMP_DIR}/lyrics", exist_ok=True)
os.makedirs(f"{SHARED_TEMP_DIR}/songs", exist_ok=True)
os.makedirs(f"{SHARED_TEMP_DIR}/output", exist_ok=True)


app = FastAPI(title="Sing Agent API", version="1.0.0")

# 全局 orchestrator 实例
_orchestrator: Optional[SingAgentOrchestrator] = None


def get_orchestrator() -> SingAgentOrchestrator:
    """获取或创建 orchestrator 实例"""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = SingAgentOrchestrator(
            output_dir=f"{SHARED_TEMP_DIR}/output",
            pregenerated_dir=f"{SHARED_TEMP_DIR}/songs"
        )
        # 更新 voice_designer 和 lyrics_generator 的目录
        _orchestrator._voice_designer.voices_dir = f"{SHARED_TEMP_DIR}/voices"
        _orchestrator._lyrics_generator.lyrics_dir = f"{SHARED_TEMP_DIR}/lyrics"
    return _orchestrator


class GenerateRequest(BaseModel):
    """歌曲生成请求"""
    voice_path: Optional[str] = Field(
        None,
        description="音色文件物理地址（绝对路径），如果为 None 则使用 voice_instructions 生成音色"
    )
    voice_instructions: Optional[str] = Field(
        None,
        description="音色描述（当 voice_path 为 None 时必填）"
    )
    theme: Optional[str] = Field(
        None,
        description="歌词主题/提示词（用于 Qwen3.6-35B 生成歌词）"
    )
    lyrics: Optional[str] = Field(
        None,
        description="歌词（如果为 None，则使用 LLM 参考 theme 生成）"
    )
    style: str = Field(
        "Pop, Happy",
        description="风格提示词"
    )
    duration: int = Field(
        90,
        description="目标时长（秒）",
        ge=30,
        le=180
    )
    pitch_shift: int = Field(
        0,
        description="音高偏移（半音）",
        ge=-12,
        le=12
    )
    model_type: str = Field(
        "acestep",
        description="生成模型类型: 'diffrhythm' 或 'acestep'（默认 acestep，不支持音频参考音色）"
    )

    def validate_model(self):
        """强校验：如果没有传入 voice_path，则 voice_instructions 必须提供"""
        if self.voice_path is None and self.voice_instructions is None:
            raise HTTPException(
                status_code=400,
                detail="voice_path 和 voice_instructions 不能同时为 None。"
                       "如果未传入音色文件(voice_path)，必须提供音色描述(voice_instructions)"
            )
        # 校验 model_type
        if self.model_type not in ["diffrhythm", "acestep"]:
            raise HTTPException(
                status_code=400,
                detail="model_type 必须是 'diffrhythm' 或 'acestep'"
            )


class GenerateResponse(BaseModel):
    """歌曲生成响应"""
    song_id: str
    song_path: str
    vocal_path: str
    voice_path: str
    lyrics: str
    status: str


class ConvertRequest(BaseModel):
    """实时转换请求"""
    song_id: str = Field(..., description="歌曲 ID（预生成歌曲）")
    voice_path: str = Field(..., description="音色文件物理地址（绝对路径）")


class ConvertDirectRequest(BaseModel):
    """直接转换请求（跳过歌曲生成）"""
    song_path: str = Field(..., description="歌曲人声路径（/data/voice-temp/songs/xxx/vocal.wav）")
    voice_path: str = Field(..., description="参考音色路径")
    pitch_shift: int = Field(0, description="音高偏移（半音）")
    n_step: int = Field(32, description="扩散步数")
    cfg: float = Field(1.0, description="cfg系数，低值减少失真")


class ConvertResponse(BaseModel):
    """实时转换响应"""
    result_path: str
    status: str


class PregenerateRequest(BaseModel):
    """预生成请求"""
    lyrics: str = Field(..., description="歌词（LRC 格式）")
    style: str = Field("Pop, Happy", description="风格提示词")
    duration: int = Field(90, description="目标时长（秒）")
    voice_path: Optional[str] = Field(None, description="参考音色文件路径（DiffRhythm 专用）")
    model_type: str = Field("acestep", description="生成模型类型: 'diffrhythm' 或 'acestep'")


class RandomSongResponse(BaseModel):
    """随机歌曲响应"""
    song_path: str
    song_id: str


@app.get("/health")
def health_check():
    """健康检查"""
    return {"status": "ok"}


@app.post("/sing/generate", response_model=GenerateResponse)
def generate_song(request: GenerateRequest, background_tasks: BackgroundTasks):
    """
    生成歌曲完整流程

    流程:
    1. 音色处理（voice_path 优先，否则用 voice_instructions 通过 Qwen3-TTS-VoiceDesign 生成）
    2. 歌词生成（lyrics 优先，否则用 theme 通过 Qwen3.6-35B 生成）
    3. DiffRhythm 生成歌曲
    4. 人声分离
    5. SoulX-Singer 音色转换

    Args:
        request: 生成请求参数

    Returns:
        生成结果，包含各阶段文件路径
    """
    # 强校验
    request.validate_model()

    try:
        orchestrator = get_orchestrator()
        model_type = ModelType(request.model_type)

        result = orchestrator.full_workflow(
            voice_path=request.voice_path,
            voice_instructions=request.voice_instructions or "清澈甜美的女声",
            theme=request.theme,
            lyrics=request.lyrics,
            style=request.style,
            duration=request.duration,
            model_type=model_type
        )

        return GenerateResponse(
            song_id=result["song_id"],
            song_path=result["song_path"],
            vocal_path=result["vocal_path"],
            voice_path=result["voice_path"],
            lyrics=result["lyrics"],
            status="completed"
        )

    except Exception as e:
        logger.error(f"Generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/sing/pregenerate")
def pregenerate_song(request: PregenerateRequest):
    """
    预生成歌曲（DiffRhythm 或 ACE-Step + 人声分离）

    不执行音色转换，保存预生成结果供后续实时转换使用

    注意: ACE-Step 不支持音频参考音色，voice_path 参数仅对 DiffRhythm 有效
    """
    try:
        orchestrator = get_orchestrator()
        song_id = f"pre_{os.getpid()}"
        model_type_enum = ModelType(request.model_type)

        container_voice_path = None
        if model_type_enum == ModelType.DIFFRHYTHM and request.voice_path:
            container_voice_path = orchestrator._voice_designer.get_container_path(request.voice_path)

        result = orchestrator.pregenerate_song(
            song_id=song_id,
            lyrics=request.lyrics,
            style=request.style,
            duration=request.duration,
            ref_audio=container_voice_path,
            model_type=model_type_enum
        )

        return {
            "song_id": result["song_id"],
            "song_path": result["song_path"],
            "vocal_path": result["vocal_path"],
            "metadata_path": result["metadata_path"],
            "model_type": request.model_type,
            "status": "ready"
        }

    except Exception as e:
        logger.error(f"Pre-generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/sing/convert", response_model=ConvertResponse)
def realtime_convert(request: ConvertRequest):
    """
    实时音色转换（SoulX-Singer）

    使用已预生成的歌曲干声 + 用户提供的音色进行转换
    """
    try:
        orchestrator = get_orchestrator()

        # 获取预生成歌曲的干声路径
        vocal_path = f"{SHARED_TEMP_DIR}/songs/{request.song_id}/vocal.wav"
        if not os.path.exists(vocal_path):
            raise HTTPException(status_code=404, detail=f"Song {request.song_id} not found")

        # 实时转换
        result_path = orchestrator.realtime_convert(
            prompt_audio=request.voice_path,
            target_vocal_path=vocal_path
        )

        return ConvertResponse(
            result_path=result_path,
            status="completed"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Conversion failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sing/songs")
def list_songs():
    """列出所有预生成歌曲"""
    songs_dir = f"{SHARED_TEMP_DIR}/songs"
    if not os.path.exists(songs_dir):
        return {"songs": []}

    songs = []
    for song_id in os.listdir(songs_dir):
        metadata_path = os.path.join(songs_dir, song_id, "metadata.json")
        if os.path.exists(metadata_path):
            import json
            with open(metadata_path) as f:
                songs.append(json.load(f))

    return {"songs": songs}


@app.get("/sing/voices")
def list_voices():
    """列出所有生成的音色文件"""
    voices_dir = f"{SHARED_TEMP_DIR}/voices"
    if not os.path.exists(voices_dir):
        return {"voices": []}

    voices = []
    for fname in os.listdir(voices_dir):
        if fname.endswith(".wav"):
            fpath = os.path.join(voices_dir, fname)
            voices.append({
                "filename": fname,
                "path": fpath,
                "size": os.path.getsize(fpath)
            })

    return {"voices": voices}


@app.post("/sing/convert-direct", response_model=ConvertResponse)
def convert_direct(request: ConvertDirectRequest):
    """
    直接音色转换（跳过歌曲生成）

    传入已有歌曲路径和参考音色，直接进行 SoulX-Singer 转换
    """
    try:
        if not os.path.exists(request.song_path):
            raise HTTPException(status_code=404, detail=f"Song not found: {request.song_path}")
        if not os.path.exists(request.voice_path):
            raise HTTPException(status_code=404, detail=f"Voice not found: {request.voice_path}")

        orchestrator = get_orchestrator()

        result_path = orchestrator.realtime_convert(
            prompt_audio=request.voice_path,
            target_vocal_path=request.song_path,
            pitch_shift=request.pitch_shift,
            n_step=request.n_step,
            cfg=request.cfg
        )

        return ConvertResponse(
            result_path=result_path,
            status="completed"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Direct conversion failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sing/random-song", response_model=RandomSongResponse)
def random_song():
    """随机返回一个已生成歌曲的路径"""
    import random

    songs_dir = f"{SHARED_TEMP_DIR}/songs"
    if not os.path.exists(songs_dir):
        raise HTTPException(status_code=404, detail="No songs available")

    song_ids = [d for d in os.listdir(songs_dir) if os.path.isdir(os.path.join(songs_dir, d))]
    if not song_ids:
        raise HTTPException(status_code=404, detail="No songs available")

    song_id = random.choice(song_ids)
    song_path = os.path.join(songs_dir, song_id, "vocal.wav")

    if not os.path.exists(song_path):
        raise HTTPException(status_code=404, detail=f"Song {song_id} vocal.wav not found")

    return RandomSongResponse(song_path=song_path, song_id=song_id)


def run_server(host: str = "0.0.0.0", port: int = 8080):
    """启动 API Server"""
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_server()