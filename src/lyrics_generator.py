"""
歌词生成模块 - Lyrics Generator Module

基于 Qwen3.6-35B 模型的歌词生成功能，参考已有歌词文件生成新歌词
"""

import os
import httpx
from typing import Optional, Dict


class LyricsGenerator:
    """歌词生成器，基于 Qwen3.6-35B API"""

    def __init__(
        self,
        llm_api_url: str = "http://localhost:40080/api/v1/chat/completions",
        auth_token: str = "Bearer hlkj2026qwen36",
        ref_lrc_path: str = "/data/script/voice/projects/DiffRhythm2/example/lrc/1.lrc",
        lyrics_dir: str = "/data/voice-temp/lyrics/"
    ):
        self.llm_url = llm_api_url
        self.auth_token = auth_token
        self.ref_lrc_path = ref_lrc_path
        self.lyrics_dir = lyrics_dir
        os.makedirs(lyrics_dir, exist_ok=True)

    def _read_reference_lrc(self) -> str:
        """读取参考歌词文件"""
        with open(self.ref_lrc_path, "r", encoding="utf-8") as f:
            return f.read()

    def _build_prompt(self, ref_lyrics: str, theme: Optional[str] = None) -> list:
        """构建给 LLM 的 prompt

        Args:
            ref_lyrics: 参考歌词
            theme: 主题描述，如果为 None 则生成相似风格

        Returns:
            消息列表
        """
        system_prompt = """你是一个专业的歌词创作者。请根据用户提供的参考歌词，创作一首新的歌词。

要求：
1. 歌词格式使用 LRC 格式，包含 [start], [intro], [verse], [chorus], [inst], [end] 等标签
2. **重要：歌词必须从头开始唱，不要有过长的纯音乐intro**，intro部分最多2秒
3. 每行歌词前用中括号标注时间戳，如 [00:15.00]
4. 歌词要有情感、有意境，避免口水话
5. **整首歌控制在30-45秒的演唱时长**
6. **确保歌词饱满，不要留太多空白时间**

参考歌词格式：
[start]
[intro]
[00:00.00][verse]
歌词内容
[00:15.00][chorus]
副歌内容
"""

        user_content = f"请参考以下歌词，创作一首新歌词。注意：新歌词要从0秒开始唱，不要有过长的intro。\n\n参考歌词：\n{ref_lyrics}"
        if theme:
            user_content += f"\n\n主题要求：{theme}"

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]

    def _call_llm(self, messages: list) -> str:
        """调用 LLM API

        Args:
            messages: 消息列表

        Returns:
            LLM 返回的歌词内容
        """
        headers = {
            "Content-Type": "application/json",
            "Authorization": self.auth_token,
        }

        payload = {
            "model": "Qwen3.6-35B-A3B",
            "messages": messages,
            "chat_template_kwargs": {"enable_thinking": False},
        }

        with httpx.Client(timeout=180.0) as client:
            response = client.post(self.llm_url, headers=headers, json=payload)
            response.raise_for_status()

            result = response.json()
            return result["choices"][0]["message"]["content"]

    def generate_lyrics(self, theme: Optional[str] = None) -> str:
        """使用 LLM 生成歌词

        Args:
            theme: 歌词主题或风格描述，如果为 None 则根据参考歌词生成相似风格

        Returns:
            生成的歌词内容 (LRC 格式字符串)
        """
        ref_lyrics = self._read_reference_lrc()
        messages = self._build_prompt(ref_lyrics, theme)
        return self._call_llm(messages)

    def save_to_file(self, lyrics: str, filename: str) -> str:
        """保存歌词到文件

        Args:
            lyrics: 歌词内容
            filename: 文件名（不含路径）

        Returns:
            保存的文件路径
        """
        filepath = os.path.join(self.lyrics_dir, filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(lyrics)

        return filepath

    def generate_and_save(self, theme: Optional[str] = None, filename: Optional[str] = None) -> Dict:
        """生成歌词并保存到文件

        Args:
            theme: 歌词主题
            filename: 保存的文件名，如果为 None 则自动生成

        Returns:
            包含 lyrics 和 file_path 的字典
        """
        lyrics = self.generate_lyrics(theme)

        if filename is None:
            import hashlib
            content_hash = hashlib.md5(lyrics.encode()).hexdigest()[:8]
            filename = f"lyrics_{content_hash}.lrc"

        filepath = self.save_to_file(lyrics, filename)

        return {
            "lyrics": lyrics,
            "file_path": filepath,
            "container_path": self._get_container_path(filepath)
        }

    def _get_container_path(self, host_path: str) -> str:
        """将宿主机路径转换为容器内路径"""
        path_mappings = {
            "/data/voice-temp/lyrics/": "/workspace/lyrics/",
            "/data/voice-temp/songs/": "/workspace/songs/",
            "/data/script/voice/projects/DiffRhythm2/example/lrc/": "/workspace/ref_lrc/",
        }

        for host_prefix, container_prefix in path_mappings.items():
            if host_path.startswith(host_prefix):
                return host_path.replace(host_prefix, container_prefix, 1)
        return host_path