"""DiffRhythm 客户端 - 歌词到歌曲生成."""

import requests
import subprocess
import logging
import os
import json
import shutil
import time as time_module
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

DIFFRHYTHM_API_URL = "http://localhost:6000"
CONTAINER_NAME = "gpu2_diff_rhythm"

# 容器内路径映射 (宿主机 -> 容器内)
CONTAINER_PATH_MAPPINGS = {
    "/data/voice-temp/voices/": "/workspace/voices/",
    "/data/voice-temp/lyrics/": "/workspace/lyrics/",
    "/data/voice-temp/songs/": "/workspace/songs/",
    "/data/voice-temp/output/": "/workspace/output/",
    "/data/DiffRhythm/output/": "/workspace/output/",
}


def get_container_path(host_path: str) -> str:
    """将宿主机路径转换为容器内路径

    Args:
        host_path: 宿主机上的文件路径

    Returns:
        容器内可访问的路径
    """
    normalized = os.path.normpath(host_path)
    for host_prefix, container_prefix in CONTAINER_PATH_MAPPINGS.items():
        if normalized.startswith(host_prefix):
            return normalized.replace(host_prefix, container_prefix, 1)
    # 默认返回原路径（假设已经在容器内可访问）
    return normalized


def wait_for_job_completion(job_id: str, timeout: int = 600, poll_interval: int = 5) -> Dict[str, Any]:
    """等待任务完成.

    Args:
        job_id: 任务ID
        timeout: 超时时间(秒)
        poll_interval: 轮询间隔(秒)

    Returns:
        任务状态字典

    Raises:
        TimeoutError: 任务超时
        RuntimeError: 任务失败
    """
    start_time = time_module.time()
    while time_module.time() - start_time < timeout:
        response = requests.get(f"{DIFFRHYTHM_API_URL}/jobs/{job_id}", timeout=10)
        if response.status_code != 200:
            raise RuntimeError(f"Failed to get job status: {response.status_code}")

        job = response.json()
        status = job.get("status")

        if status == "completed":
            return job
        elif status == "failed":
            raise RuntimeError(f"Generation failed: {job.get('error')}")

        logger.debug(f"Job {job_id} status: {status}, waiting...")
        time_module.sleep(poll_interval)

    raise TimeoutError(f"Job {job_id} timed out after {timeout}s")


def generate_song_with_diffrhythm(
    lyrics: str,
    song_name: str = "generated_song",
    style: str = "Pop, Happy",
    duration: int = 90,
    steps: int = 64,
    cfg_strength: float = 1.5,
    ref_audio: str = None,
    wait: bool = True,
    timeout: int = 600
) -> str:
    """使用 DiffRhythm API 生成歌曲.

    注意: steps=64 + cfg=1.5 是唯一能达到可接受人声音质的配置。
    其他参数组合生成的音质极差，无法使用。

    Args:
        lyrics: 歌词文本 (LRC格式支持)
        song_name: 生成歌曲的名称
        style: 风格提示词 (可以是文本描述或音频文件路径)
        duration: 目标时长 (秒)
        steps: 采样步数 (默认64，高质量；16为快速预览但质量差)
        cfg_strength: CFG强度 (默认1.5，自然；2.0以上会过于尖锐)
        ref_audio: 参考音频路径 (宿主机路径，会自动转换为容器内路径)
        wait: 是否等待生成完成 (True=同步, False=异步返回job_id)
        timeout: 等待超时时间(秒)

    Returns:
        生成的歌曲文件路径 (wait=True时)
        包含job_id的字典 (wait=False时)

    Raises:
        RuntimeError: 如果生成失败
    """
    style_prompt = style

    # 如果提供了 ref_audio，需要将其放到容器内可访问的位置
    if ref_audio:
        # 如果是容器内路径（/workspace/ 或 /tmp/ 开头），直接使用
        if ref_audio.startswith("/workspace/") or ref_audio.startswith("/tmp/"):
            style_prompt = ref_audio
            logger.info(f"Using container ref_audio path: {style_prompt}")
        else:
            # 否则是宿主机路径，需要复制到容器内
            if not os.path.exists(ref_audio):
                raise FileNotFoundError(f"Reference audio not found: {ref_audio}")

            # 复制到容器的 /tmp 目录
            container_ref_path = f"/tmp/{song_name}_ref.wav"
            subprocess.run(
                ["docker", "cp", ref_audio, f"{CONTAINER_NAME}:{container_ref_path}"],
                check=True,
                capture_output=True,
                timeout=30
            )
            style_prompt = container_ref_path
            logger.info(f"Copied ref_audio to container: {style_prompt}")

    # 保存歌词到临时文件（DiffRhythm 需要 LRC 文件路径）
    lrc_path = f"/tmp/{song_name}_input.lrc"
    with open(lrc_path, "w", encoding="utf-8") as f:
        f.write(lyrics)

    # 调用 HTTP API
    payload = {
        "lyrics": lrc_path,  # 传入文件路径而不是内容
        "style_prompt": style_prompt,
        "duration": float(duration),
        "cfg_strength": cfg_strength,
        "steps": steps,
        "song_name": song_name
    }

    try:
        response = requests.post(
            f"{DIFFRHYTHM_API_URL}/generate",
            json=payload,
            timeout=30  # 提交请求30秒超时
        )

        if response.status_code != 202:
            raise RuntimeError(f"DiffRhythm API error: {response.status_code} - {response.text}")

        result = response.json()
        job_id = result.get("job_id")

        if not wait:
            return {"job_id": job_id, "status_url": result.get("check_status")}

        # 等待任务完成
        logger.info(f"Waiting for job {job_id} to complete...")
        job_result = wait_for_job_completion(job_id, timeout=timeout)

        # 下载文件
        output_file = f"/tmp/{song_name}_output.wav"
        download_response = requests.get(
            f"{DIFFRHYTHM_API_URL}/download/{job_id}",
            timeout=60
        )
        if download_response.status_code != 200:
            raise RuntimeError(f"Failed to download: {download_response.status_code}")

        with open(output_file, "wb") as f:
            f.write(download_response.content)

        logger.info(f"Song generated: {output_file}")
        return output_file

    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Failed to connect to DiffRhythm API: {e}")


class DiffRhythmClient:
    """DiffRhythm 客户端封装类."""

    def __init__(self, api_url: str = DIFFRHYTHM_API_URL, check_container: bool = True):
        """初始化 DiffRhythm 客户端.

        Args:
            api_url: DiffRhythm API 服务器地址
            check_container: 是否检查容器状态
        """
        self.api_url = api_url
        self._check_container = check_container
        self._container_name = CONTAINER_NAME

    def generate(
        self,
        lyrics: str,
        song_name: str = "generated_song",
        style: str = "Pop, Happy",
        duration: int = 90,
        steps: int = 16,
        cfg_strength: float = 2.0,
        ref_audio: str = None,
        wait: bool = True,
        timeout: int = 600
    ) -> str:
        """封装 generate_song_with_diffrhythm.

        Args:
            lyrics: 歌词文本
            song_name: 歌曲名称
            style: 风格提示词
            duration: 目标时长
            steps: 采样步数
            cfg_strength: CFG强度
            ref_audio: 参考音频路径 (用于提供人声参考)
            wait: 是否等待生成完成
            timeout: 等待超时时间(秒)

        Returns:
            生成的歌曲路径
        """
        return generate_song_with_diffrhythm(
            lyrics=lyrics,
            song_name=song_name,
            style=style,
            duration=duration,
            steps=steps,
            cfg_strength=cfg_strength,
            ref_audio=ref_audio,
            wait=wait,
            timeout=timeout
        )

    def get_job_status(self, job_id: str) -> dict:
        """获取任务状态.

        Args:
            job_id: 任务ID

        Returns:
            任务状态字典
        """
        response = requests.get(f"{self.api_url}/jobs/{job_id}", timeout=10)
        if response.status_code != 200:
            raise RuntimeError(f"Failed to get job status: {response.status_code}")
        return response.json()

    def download_result(self, job_id: str, output_path: str = None) -> str:
        """下载生成结果.

        Args:
            job_id: 任务ID
            output_path: 保存路径，默认 /tmp/<job_id>.wav

        Returns:
            保存的文件路径
        """
        if output_path is None:
            output_path = f"/tmp/{job_id}.wav"

        response = requests.get(f"{self.api_url}/download/{job_id}", timeout=60)
        if response.status_code != 200:
            raise RuntimeError(f"Failed to download: {response.status_code}")

        with open(output_path, "wb") as f:
            f.write(response.content)
        return output_path

    def is_ready(self) -> bool:
        """检查服务是否就绪."""
        try:
            response = requests.get(f"{self.api_url}/health", timeout=5)
            if response.status_code == 200:
                data = response.json()
                return data.get("model_loaded", False)
        except Exception:
            pass
        return False

    def get_status(self) -> dict:
        """获取服务状态."""
        try:
            response = requests.get(f"{self.api_url}/health", timeout=5)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            return {"status": "error", "error": str(e)}
        return {"status": "unknown"}