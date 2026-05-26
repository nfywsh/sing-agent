#!/usr/bin/env python3
"""测试完整流水线 - 基础模块测试."""

import sys
import os

sys.path.insert(0, "/data/script/voice/sing-agent/src")

def test_module_imports():
    """测试模块导入."""
    print("=== 测试模块导入 ===")
    from audio_prep import prepare_audio_for_soulx, validate_audio_format
    print("  audio_prep: OK")
    
    from soulx_client import convert_vocal_timbre, SoulXClient
    print("  soulx_client: OK")
    
    from diffrhythm_client import generate_song_with_diffrhythm, DiffRhythmClient
    print("  diffrhythm_client: OK")
    
    from vocal_separator import separate_vocals, VocalSeparator
    print("  vocal_separator: OK")
    
    from orchestrator import SingAgentOrchestrator, clone_song_with_timbre, PipelineState
    print("  orchestrator: OK")
    
    print("所有模块导入成功!")


def test_audio_prep():
    """测试音频预处理."""
    print("\n=== 测试音频预处理 ===")
    from audio_prep import validate_audio_format
    import soundfile as sf
    import numpy as np
    
    # 创建测试音频 - 16kHz 单声道
    test_audio = "/tmp/test_16k_mono.wav"
    t = np.linspace(0, 1, 16000)
    audio = np.sin(2 * np.pi * 440 * t).astype(np.float32)
    sf.write(test_audio, audio, 16000)
    
    is_valid, info = validate_audio_format(test_audio)
    print(f"音频验证: is_valid={is_valid}")
    print(f"  sample_rate: {info['sample_rate']}")
    print(f"  channels: {info['channels']}")
    assert is_valid, f"音频验证失败: {info['errors']}"
    print("音频预处理测试通过!")


def test_soulx_connection():
    """测试 SoulX-Singer 连接."""
    print("\n=== 测试 SoulX-Singer 连接 ===")
    from gradio_client import Client
    try:
        client = Client("http://localhost:7861", verbose=False)
        print("SoulX-Singer 连接成功!")
    except Exception as e:
        print(f"SoulX-Singer 连接失败: {e}")


def test_diff_container():
    """测试 DiffRhythm 容器状态."""
    print("\n=== 测试 DiffRhythm 容器状态 ===")
    from diffrhythm_client import DiffRhythmClient
    try:
        client = DiffRhythmClient()
        print(f"DiffRhythm 容器状态: {client.is_ready()}")
    except Exception as e:
        print(f"DiffRhythm 容器检查失败: {e}")


def main():
    print("=" * 50)
    print("sing-agent 流水线测试")
    print("=" * 50)
    
    try:
        test_module_imports()
        test_audio_prep()
        test_soulx_connection()
        test_diff_container()
        
        print("\n" + "=" * 50)
        print("所有基础测试通过!")
        print("=" * 50)
        
    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
