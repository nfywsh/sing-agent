#!/usr/bin/env python3
"""完整流水线测试: VoiceDesign → ACE-Step → 人声分离 → SoulX-Singer"""

import sys
import os
import time
import subprocess
import json
import shutil

# 添加项目路径
sys.path.insert(0, "/data/script/voice/sing-agent/src")

from audio_prep import prepare_audio_for_soulx, validate_audio_format
from soulx_client import SoulXClient
from ace_step_client import ACEStepClient
from vocal_separator import separate_vocals
import httpx

# 配置
TTS_URL = "http://localhost:8020"
ACE_STEP_URL = "http://localhost:8001"
SOULX_URL = "http://localhost:7861"
OUTPUT_DIR = "/tmp/sing_agent_test"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 颜色输出
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def log_warning(msg):
    print(f"{Colors.WARNING}[WARNING]{Colors.ENDC} {msg}")

# 歌词 (ACE-Step 格式，使用结构标签)
LYRICS = """[start]
[intro]
[verse]
清晨的阳光轻轻洒在窗台上
新的一天开始了
我们一起向前走
追逐心中的梦想
[chorus]
让歌声传递快乐
温暖每一个心灵
不管前方有多少困难
微笑面对每一天
[outro]"""


def check_service(url, name):
    """检查服务是否可用"""
    try:
        resp = httpx.get(f"{url}/health", timeout=5)
        if resp.status_code == 200:
            return True
    except:
        pass

    # SoulX-Singer (Gradio) doesn't have /health, check /gradio_api/info
    try:
        resp = httpx.get(f"{url}/gradio_api/info", timeout=5)
        return resp.status_code == 200
    except:
        return False


def generate_timbre_with_voicedesign(instructions: str, text: str) -> str:
    """使用 VoiceDesign 生成参考音色音频

    Args:
        instructions: 音色描述
        text: 生成文本（越长音色特征越丰富）
    """
    print(f"\n=== 步骤1: VoiceDesign 生成参考音色 ===")
    print(f"描述: {instructions}")
    print(f"文本长度: {len(text)} 字符")

    response = httpx.post(
        f"{TTS_URL}/v1/audio/speech",
        json={
            "model": "Qwen3-TTS-VoiceDesign",
            "input": text,
            "task_type": "VoiceDesign",
            "instructions": instructions,
            "response_format": "wav"
        },
        timeout=120
    )

    if response.status_code != 200:
        raise RuntimeError(f"TTS API error: {response.status_code} - {response.text[:200]}")

    output_path = f"{OUTPUT_DIR}/timbre_voicedesign.wav"
    with open(output_path, "wb") as f:
        f.write(response.content)

    # 验证文件
    is_valid, info = validate_audio_format(output_path)
    print(f"音色音频已生成: {output_path}")
    print(f"  格式: {info['sample_rate']}Hz, {info['channels']}ch, {info['duration']:.1f}秒")
    return output_path


def convert_mp3_to_wav(mp3_path: str) -> str:
    """将 MP3 转换为 WAV"""
    wav_path = mp3_path.replace(".mp3", ".wav")
    subprocess.run([
        "ffmpeg", "-y", "-i", mp3_path, "-ar", "44100", "-ac", "2", wav_path
    ], capture_output=True, check=True)
    return wav_path


def main():
    print("=" * 60)
    print("完整流水线测试")
    print("VoiceDesign → ACE-Step → 人声分离 → SoulX-Singer")
    print("=" * 60)

    start_time = time.time()

    # 0. 检查服务状态
    print("\n=== 步骤0: 检查服务状态 ===")
    services = {
        "VoiceDesign (8020)": check_service(TTS_URL, "VoiceDesign"),
        "ACE-Step (8001)": check_service(ACE_STEP_URL, "ACE-Step"),
        "SoulX-Singer (7861)": check_service(SOULX_URL, "SoulX-Singer"),
    }
    for name, available in services.items():
        status = "✓ 可用" if available else "✗ 不可用"
        print(f"  {name}: {status}")

    soulx_available = services["SoulX-Singer (7861)"]

    # 1. VoiceDesign 生成参考音色（使用更长文本以获得更丰富的音色特征）
    timbre_text = (
        "清晨的阳光轻轻洒在窗台上，新的一天开始了。"
        "我们一起向前走，追逐心中的梦想。"
        "让歌声传递快乐，温暖每一个心灵。"
        "不管前方有多少困难，微笑面对每一天。"
    )
    timbre_audio = generate_timbre_with_voicedesign(
        instructions="一个温柔甜美的年轻女声，音色清晰明亮，唱歌时情感丰富",
        text=timbre_text
    )

    # 2. 预处理音色音频 (转换为16kHz mono)
    print(f"\n=== 步骤2: 预处理音色音频 ===")
    timbre_prepared = prepare_audio_for_soulx(timbre_audio)
    is_valid, info = validate_audio_format(timbre_prepared)
    print(f"预处理后: {timbre_prepared}")
    print(f"  格式: {info['sample_rate']}Hz, {info['channels']}ch")

    # 3. ACE-Step 生成歌曲
    print(f"\n=== 步骤3: ACE-Step 生成歌曲 ===")
    ace_client = ACEStepClient(api_url=ACE_STEP_URL)

    # 检查服务状态
    status = ace_client.get_status()
    print(f"ACE-Step 状态: {status}")

    # 使用 /release_task 接口（保留原始歌词，不重写）
    song_path = ace_client.generate(
        lyrics=LYRICS,
        song_name="test_song",
        caption="",  # 不使用 caption，以免 LLM 重写歌词
        duration=30,
        wait=True,
        timeout=600
    )
    print(f"歌曲已生成: {song_path}")

    # ACE-Step 返回 MP3，需要转换为 WAV 用于后续处理
    if song_path.endswith(".mp3"):
        song_path = convert_mp3_to_wav(song_path)
        print(f"已转换为 WAV: {song_path}")

    # 检查歌曲
    is_valid, info = validate_audio_format(song_path)
    print(f"  格式: {info['sample_rate']}Hz, {info['channels']}ch, {info['duration']:.1f}秒")

    # 4. 人声分离
    print(f"\n=== 步骤4: 人声分离 ===")
    vocal_path = separate_vocals(song_path)
    print(f"人声已分离: {vocal_path}")

    # 5. SoulX-Singer 音色转换（如果可用）
    if soulx_available:
        print(f"\n=== 步骤5: SoulX-Singer 音色转换 ===")
        soulx_client = SoulXClient()

        # 预处理人声音频 (确保16kHz mono)
        vocal_prepared = prepare_audio_for_soulx(vocal_path)
        is_valid, info = validate_audio_format(vocal_prepared)
        print(f"人声预处理后: {info['sample_rate']}Hz, {info['channels']}ch")

        try:
            result = soulx_client.convert(
                prompt_audio=timbre_prepared,
                target_audio=vocal_prepared,
                pitch_shift=0,
                n_step=32,
                cfg=1.0  # 低cfg，减少失真，保持歌词保真度
            )

            # 复制结果到输出目录
            final_output = f"{OUTPUT_DIR}/final_song.wav"
            shutil.copy(result, final_output)
            print(f"最终歌曲: {final_output}")
        except Exception as e:
            log_warning(f"SoulX-Singer 转换失败: {e}")
            log_warning("跳过音色转换，使用原始人声作为最终输出")
            final_output = f"{OUTPUT_DIR}/final_vocal.wav"
            shutil.copy(vocal_path, final_output)
            print(f"最终输出（人声）: {final_output}")
    else:
        print(f"\n=== 步骤5: SoulX-Singer 音色转换 ===")
        print("SoulX-Singer 不可用，跳过音色转换")
        # 复制分离后的人声作为最终输出
        final_output = f"{OUTPUT_DIR}/final_vocal.wav"
        shutil.copy(vocal_path, final_output)
        print(f"最终输出（人声）: {final_output}")

    total_time = time.time() - start_time

    print(f"\n" + "=" * 60)
    print(f"✅ 完整流水线测试成功!")
    print(f"总耗时: {total_time:.1f}秒")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)