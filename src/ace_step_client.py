"""ACE-Step 客户端 - 歌词到歌曲生成."""

import httpx
import logging
import os
import json
import time as time_module
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

ACE_STEP_API_URL = os.environ.get("ACE_STEP_URL", "http://localhost:8001")
CONTAINER_NAME = "gpu2_diff_rhythm"

# 超时配置
TIMEOUTS = {
    "connect": 10.0,
    "read": 120.0,  # ACE-Step 模型初始化可能需要较长时间
    "write": 30.0,
    "pool": 30.0,
}


def wait_for_task_completion(task_id: str, timeout: int = 600, poll_interval: int = 5) -> Dict[str, Any]:
    """等待任务完成.

    Args:
        task_id: 任务ID
        timeout: 超时时间(秒)
        poll_interval: 轮询间隔(秒)

    Returns:
        任务结果字典

    Raises:
        TimeoutError: 任务超时
        RuntimeError: 任务失败
    """
    start_time = time_module.time()

    with httpx.Client(timeout=httpx.Timeout(120.0, read=120.0)) as client:
        while time_module.time() - start_time < timeout:
            try:
                response = client.post(
                    f"{ACE_STEP_API_URL}/query_result",
                    json={"task_id_list": [task_id]}
                )

                if response.status_code != 200:
                    raise RuntimeError(f"Failed to query task: {response.status_code}")

                result = response.json()
                data = result.get("data", [{}])[0]
                status = data.get("status")

                if status == 1:  # Completed
                    result_str = data.get("result", "[]")
                    # result 是 JSON 字符串，需要解析
                    if isinstance(result_str, str):
                        result_list = json.loads(result_str)
                    else:
                        result_list = result_str
                    return result_list[0] if result_list else {}
                elif status == 3:  # Failed
                    raise RuntimeError(f"ACE-Step generation failed")

                logger.debug(f"Task {task_id} status: {status}, waiting...")
                time_module.sleep(poll_interval)

            except httpx.TimeoutException:
                logger.warning(f"Query timeout, retrying... (elapsed: {time_module.time() - start_time:.1f}s)")
                continue

    raise TimeoutError(f"Task {task_id} timed out after {timeout}s")


def generate_song_with_acestep(
    lyrics: str,
    song_name: str = "generated_song",
    caption: str = "",
    duration: int = 30,
    wait: bool = True,
    timeout: int = 600
) -> str:
    """使用 ACE-Step API 生成歌曲.

    Args:
        lyrics: 歌词文本 (带结构标签格式)
        song_name: 生成歌曲的名称
        caption: 风格描述（可选，会让LLM重写歌词）
        duration: 目标时长 (秒)
        wait: 是否等待生成完成 (True=同步, False=异步返回task_id)
        timeout: 等待超时时间(秒)

    Returns:
        生成的歌曲文件路径 (wait=True时)
        包含task_id的字典 (wait=False时)

    Raises:
        RuntimeError: 如果生成失败
    """
    # 使用 /release_task 保留原始歌词（不重写）
    payload = {
        "lyrics": lyrics,
        "audio_duration": float(duration),
    }

    # 如果提供了 caption 且不为空，才传入（会导致歌词被重写）
    if caption:
        payload["prompt"] = caption
        # 使用 create_sample 接口
        endpoint = f"{ACE_STEP_API_URL}/v1/create_sample"
        payload["song_name"] = song_name
    else:
        # 使用 release_task 接口（保留歌词）
        endpoint = f"{ACE_STEP_API_URL}/release_task"

    try:
        # 使用较长超时，因为模型可能需要初始化
        with httpx.Client(timeout=httpx.Timeout(120.0, read=300.0)) as client:
            response = client.post(endpoint, json=payload)

        if response.status_code != 200:
            raise RuntimeError(f"ACE-Step API error: {response.status_code} - {response.text}")

        result = response.json()
        task_id = result.get("data", {}).get("task_id")

        if not task_id:
            raise RuntimeError(f"No task_id returned: {result}")

        if not wait:
            return {"task_id": task_id, "endpoint": endpoint}

        # 等待任务完成
        logger.info(f"Waiting for task {task_id} to complete...")
        task_result = wait_for_task_completion(task_id, timeout=timeout)

        # 获取生成的文件路径
        file_path = task_result.get("file")
        if not file_path:
            raise RuntimeError(f"No file path in task result: {task_result}")

        # 下载文件
        output_file = f"/tmp/{song_name}_output.mp3"

        with httpx.Client(timeout=httpx.Timeout(60.0, read=120.0)) as client:
            if "path=" in file_path:
                encoded_path = file_path.split("path=")[1]
                download_url = f"{ACE_STEP_API_URL}/v1/audio?path={encoded_path}"
            else:
                download_url = f"{ACE_STEP_API_URL}{file_path}"

            download_response = client.get(download_url)
            if download_response.status_code != 200:
                raise RuntimeError(f"Failed to download: {download_response.status_code}")

            with open(output_file, "wb") as f:
                f.write(download_response.content)

        logger.info(f"Song generated: {output_file}")
        return output_file

    except httpx.TimeoutException as e:
        raise RuntimeError(f"ACE-Step API timeout: {e}")
    except httpx.RequestError as e:
        raise RuntimeError(f"Failed to connect to ACE-Step API: {e}")


class ACEStepClient:
    """ACE-Step 客户端封装类."""

    def __init__(self, api_url: str = ACE_STEP_API_URL):
        """初始化 ACE-Step 客户端.

        Args:
            api_url: ACE-Step API 服务器地址
        """
        self.api_url = api_url
        self._client = httpx.Client(
            timeout=httpx.Timeout(120.0, read=300.0),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._client.close()

    def generate(
        self,
        lyrics: str,
        song_name: str = "generated_song",
        caption: str = "",
        duration: int = 30,
        wait: bool = True,
        timeout: int = 600
    ) -> str:
        """封装 generate_song_with_acestep.

        Args:
            lyrics: 歌词文本
            song_name: 歌曲名称
            caption: 风格描述
            duration: 目标时长
            wait: 是否等待生成完成
            timeout: 等待超时时间(秒)

        Returns:
            生成的歌曲路径
        """
        return generate_song_with_acestep(
            lyrics=lyrics,
            song_name=song_name,
            caption=caption,
            duration=duration,
            wait=wait,
            timeout=timeout
        )

    def get_task_status(self, task_id: str) -> dict:
        """获取任务状态.

        Args:
            task_id: 任务ID

        Returns:
            任务状态字典
        """
        response = self._client.post(
            f"{self.api_url}/query_result",
            json={"task_id_list": [task_id]}
        )
        if response.status_code != 200:
            raise RuntimeError(f"Failed to query task: {response.status_code}")
        return response.json()

    def download_result(self, file_path: str, output_path: str = None) -> str:
        """下载生成结果.

        Args:
            file_path: 文件路径（来自任务结果）
            output_path: 保存路径，默认 /tmp/<hash>.mp3

        Returns:
            保存的文件路径
        """
        if output_path is None:
            output_path = f"/tmp/acestep_result.mp3"

        if "path=" in file_path:
            encoded_path = file_path.split("path=")[1]
            download_url = f"{self.api_url}/v1/audio?path={encoded_path}"
        else:
            download_url = f"{self.api_url}{file_path}"

        response = self._client.get(download_url)
        if response.status_code != 200:
            raise RuntimeError(f"Failed to download: {response.status_code}")

        with open(output_path, "wb") as f:
            f.write(response.content)
        return output_path

    def is_ready(self) -> bool:
        """检查服务是否就绪."""
        try:
            response = self._client.get(f"{self.api_url}/health", timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                return data.get("data", {}).get("llm_initialized", False)
        except Exception:
            pass
        return False

    def get_status(self) -> dict:
        """获取服务状态."""
        try:
            response = self._client.get(f"{self.api_url}/health", timeout=5.0)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            return {"status": "error", "error": str(e)}
        return {"status": "unknown"}