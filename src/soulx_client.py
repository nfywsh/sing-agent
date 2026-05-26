"""
SoulX-Singer Voice Timbre Conversion Client

调用 SoulX-Singer 进行音色转换，基于 gradio_client.
"""

import os
import time
import logging
import shutil
from pathlib import Path
from typing import Optional

from gradio_client import Client, handle_file

logger = logging.getLogger(__name__)

# SoulX-Singer 服务地址 (支持环境变量覆盖)
SOULX_SERVER_URL = os.environ.get("SOULX_URL", "http://localhost:7861")
SOULX_API_NAME = "/_start_svc"

# SoulX-Singer 容器名称
SOULX_CONTAINER_NAME = "gpu2_soulx_singer"

# 输出目录映射 (容器内 -> 宿主机)
SOULX_OUTPUT_PATH_MAPPINGS = {
    "/tmp/gradio/": "/data/voice-temp/output/",
    "/workspace/output/": "/data/voice-temp/output/",
}


def _convert_container_path_to_host(container_path: str) -> str:
    """将容器内路径转换为宿主机路径

    Args:
        container_path: 容器内返回的路径

    Returns:
        宿主机上可访问的路径
    """
    container_path = os.path.normpath(container_path)

    # 检查是否是容器内部路径需要转换
    for container_prefix, host_prefix in SOULX_OUTPUT_PATH_MAPPINGS.items():
        if container_path.startswith(container_prefix):
            return container_path.replace(container_prefix, host_prefix, 1)

    # 如果路径已经在 /data/voice-temp/ 下，保持不变
    if container_path.startswith("/data/voice-temp/"):
        return container_path

    # 其他情况，复制到标准输出目录
    filename = os.path.basename(container_path)
    host_path = f"/data/voice-temp/output/{filename}"
    logger.warning(f"Unknown container path {container_path}, copying to {host_path}")
    return host_path


def convert_vocal_timbre(
    prompt_audio: str,
    target_audio: str,
    pitch_shift: int = 0,
    n_step: int = 32,
    cfg: float = 1.0,
    seed: int = 42,
) -> str:
    """
    使用 SoulX-Singer 进行音色转换.

    Args:
        prompt_audio: 参考音色音频路径 (16kHz mono WAV) - 宿主机路径
        target_audio: 目标音频路径 (16kHz mono WAV) - 宿主机路径
        pitch_shift: 音高偏移 (半音)
        n_step: 扩散步数
        cfg: 引导强度
        seed: 随机种子

    Returns:
        转换后的音频文件路径 (宿主机路径)
    """
    client = Client(SOULX_SERVER_URL, verbose=False)

    # 使用 gradio_client.handle_file 上传本地文件
    prompt_file = handle_file(str(Path(prompt_audio).resolve()))
    target_file = handle_file(str(Path(target_audio).resolve()))

    try:
        result = client.predict(
            prompt_file,
            target_file,
            False,  # prompt_vocal_sep
            False,  # target_vocal_sep
            False,  # auto_shift
            False,  # auto_mix_acc
            pitch_shift,
            n_step,
            cfg,
            seed,
            api_name=SOULX_API_NAME,
        )
    except Exception as e:
        logger.error(f"SoulX-Singer predict failed: {e}")
        raise

    logger.info(f"SoulX-Singer raw result: {result}, type: {type(result)}")

    # Debug: log more details about the result
    if result is not None:
        logger.info(f"SoulX-Singer result content: {repr(result)[:500]}")

    # result 可能返回文件路径或元组
    if isinstance(result, tuple):
        container_output_path = result[0]
    elif result is None:
        # API 调用可能失败但没有抛出异常
        logger.warning(f"SoulX-Singer returned None, API may have failed silently")
        raise RuntimeError("SoulX-Singer conversion returned no result")
    else:
        container_output_path = result

    if container_output_path is None:
        raise RuntimeError("SoulX-Singer conversion returned None path")

    # 延迟约3秒确保输出文件写入完成
    time.sleep(3)

    logger.info(f"SoulX-Singer container output: {container_output_path}")

    # 转换为宿主机路径
    host_output_path = _convert_container_path_to_host(container_output_path)

    # 如果路径不同，需要复制文件
    if host_output_path != container_output_path and os.path.exists(container_output_path):
        os.makedirs(os.path.dirname(host_output_path), exist_ok=True)
        shutil.copy2(container_output_path, host_output_path)
        logger.info(f"Copied output to host: {host_output_path}")

    return host_output_path


class SoulXClient:
    """
    SoulX-Singer 客户端封装类.
    """

    def __init__(self, server_url: str = SOULX_SERVER_URL, max_retries: int = 3):
        """
        初始化 SoulX 客户端.

        Args:
            server_url: SoulX-Singer 服务地址
            max_retries: 最大重试次数
        """
        self.server_url = server_url
        self.max_retries = max_retries
        self._client = Client(server_url, verbose=False)

    def convert(
        self,
        prompt_audio: str,
        target_audio: str,
        pitch_shift: int = 0,
        n_step: int = 32,
        cfg: float = 1.0,
        seed: int = 42,
    ) -> str:
        """
        封装 convert_vocal_timbre, 带重试机制.

        Args:
            prompt_audio: 参考音色音频路径 (宿主机路径)
            target_audio: 目标音频路径 (宿主机路径)
            pitch_shift: 音高偏移
            n_step: 扩散步数
            cfg: 引导强度
            seed: 随机种子

        Returns:
            转换后的音频文件路径 (宿主机路径)
        """
        last_error = None

        for attempt in range(self.max_retries):
            try:
                return convert_vocal_timbre(
                    prompt_audio=prompt_audio,
                    target_audio=target_audio,
                    pitch_shift=pitch_shift,
                    n_step=n_step,
                    cfg=cfg,
                    seed=seed,
                )
            except Exception as e:
                last_error = e
                logger.warning(
                    f"Attempt {attempt + 1}/{self.max_retries} failed: {e}"
                )
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)  # 指数退避

        raise RuntimeError(
            f"SoulX-Singer conversion failed after {self.max_retries} attempts"
        ) from last_error