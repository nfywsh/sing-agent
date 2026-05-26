import os
import hashlib
import httpx
from typing import Dict, Tuple, Optional


class VoiceDesigner:
    """音色设计模块，使用 Qwen3-TTS-VoiceDesign 生成音色"""

    def __init__(
        self,
        tts_api_url: str = "http://localhost:40080/tts/vd/v1/audio/speech",
        voices_dir: str = "/data/voice-temp/voices/"
    ):
        self.tts_url = tts_api_url
        self.voices_dir = voices_dir
        os.makedirs(voices_dir, exist_ok=True)

        # 路径映射表 (宿主机路径 -> 容器内路径)
        self.PATH_MAPPINGS: Dict[str, str] = {
            "/data/voice-temp/voices/": "/workspace/voices/",
            "/data/voice-temp/lyrics/": "/workspace/lyrics/",
            "/data/voice-temp/songs/": "/workspace/songs/",
            "/data/voice-temp/output/": "/workspace/output/",
            "/data/script/voice/projects/DiffRhythm2/example/lrc/": "/workspace/ref_lrc/",
            "/data/DiffRhythm/output/": "/workspace/output/",
        }

    def _calculate_file_hash(self, file_path: str) -> str:
        """计算文件的 MD5 hash"""
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def get_container_path(self, host_path: str) -> str:
        """将宿主机路径转换为容器内路径"""
        for host_prefix, container_prefix in self.PATH_MAPPINGS.items():
            if host_path.startswith(host_prefix):
                return host_path.replace(host_prefix, container_prefix, 1)
        return host_path

    def is_same_voice(self, voice_path1: str, voice_path2: str) -> bool:
        """通过文件 hash 判断两个音色文件是否相同"""
        if not os.path.exists(voice_path1) or not os.path.exists(voice_path2):
            return False
        hash1 = self._calculate_file_hash(voice_path1)
        hash2 = self._calculate_file_hash(voice_path2)
        return hash1 == hash2

    def use_existing_voice(self, voice_path: str) -> Dict:
        """使用已存在的音色文件（用户上传）

        Args:
            voice_path: 音色文件路径

        Returns:
            包含 host_path 和 container_path 的字典
        """
        if not os.path.exists(voice_path):
            raise FileNotFoundError(f"Voice file not found: {voice_path}")

        return {
            "host_path": voice_path,
            "container_path": self.get_container_path(voice_path)
        }

    def design_voice(self, instructions: str, output_filename: Optional[str] = None) -> Dict:
        """使用 Qwen3-TTS-VoiceDesign 生成音色

        Args:
            instructions: 音色描述（如"清澈甜美的女声"）
            output_filename: 可选的输出文件名

        Returns:
            包含 host_path 和 container_path 的字典
        """
        if output_filename is None:
            output_filename = f"voice_{hashlib.md5(instructions.encode()).hexdigest()[:8]}.wav"

        host_path = os.path.join(self.voices_dir, output_filename)
        container_path = self.get_container_path(host_path)

        # VoiceDesign 需要用实际的语音文本作为 input 来生成足够的音频样本
        # 使用约10秒的中文文本确保生成足够长的参考音频
        sample_text = "清晨的阳光轻轻洒在窗台上，新的一天开始了。希望今天也是美好的一天，充满温暖和快乐。"

        payload = {
            "model": "Qwen3-TTS-VoiceDesign",
            "input": sample_text,
            "task_type": "VoiceDesign",
            "instructions": instructions,
            "response_format": "wav"
        }

        with httpx.Client(timeout=120.0) as client:
            response = client.post(self.tts_url, json=payload)
            response.raise_for_status()

            # 确保目录存在
            os.makedirs(os.path.dirname(host_path), exist_ok=True)

            # 写入文件
            with open(host_path, "wb") as f:
                f.write(response.content)

        return {
            "host_path": host_path,
            "container_path": container_path
        }