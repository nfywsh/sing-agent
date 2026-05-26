#!/usr/bin/env python3
"""
Sing Agent 测试脚本

测试场景:
1. 输入歌词 + 一个音色 → 生成音乐
2. 输入歌词 + 两个音色（基础 + 替换）→ 生成音乐
3. 输入已有音乐文件 + 替换音色 → 生成音乐
"""

import os
import sys
import time
import requests
import json
import subprocess
import argparse
from pathlib import Path

# 配置
API_BASE = "http://localhost:8080"
SHARED_TEMP_DIR = "/data/voice-temp"

# 颜色输出
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def log_info(msg):
    print(f"{Colors.OKBLUE}[INFO]{Colors.ENDC} {msg}")


def log_success(msg):
    print(f"{Colors.OKGREEN}[SUCCESS]{Colors.ENDC} {msg}")


def log_warning(msg):
    print(f"{Colors.WARNING}[WARNING]{Colors.ENDC} {msg}")


def log_error(msg):
    print(f"{Colors.FAIL}[ERROR]{Colors.ENDC} {msg}")


def check_api_health():
    """检查 API 服务是否正常运行"""
    try:
        resp = requests.get(f"{API_BASE}/health", timeout=5)
        if resp.status_code == 200:
            log_success("API 服务正常运行")
            return True
    except Exception as e:
        log_error(f"API 服务不可用: {e}")
        return False
    return False


def get_audio_duration(file_path):
    """获取音频文件时长（秒）"""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "json", file_path],
            capture_output=True, text=True, timeout=10
        )
        data = json.loads(result.stdout)
        return float(data["format"]["duration"])
    except Exception as e:
        log_warning(f"无法获取音频时长: {e}")
        return None


def list_existing_voices():
    """列出已有的音色文件"""
    voices_dir = f"{SHARED_TEMP_DIR}/voices"
    if not os.path.exists(voices_dir):
        return []

    voices = []
    for fname in os.listdir(voices_dir):
        if fname.endswith(".wav"):
            fpath = os.path.join(voices_dir, fname)
            duration = get_audio_duration(fpath)
            voices.append({
                "filename": fname,
                "path": fpath,
                "duration": duration
            })
    return voices


def list_existing_songs():
    """列出已有的预生成歌曲"""
    songs_dir = f"{SHARED_TEMP_DIR}/songs"
    if not os.path.exists(songs_dir):
        return []

    songs = []
    for song_id in os.listdir(songs_dir):
        metadata_path = os.path.join(songs_dir, song_id, "metadata.json")
        if os.path.exists(metadata_path):
            with open(metadata_path) as f:
                songs.append(json.load(f))
    return songs


# ============== 测试场景 ==============

def test_scenario_1_one_voice(model_type="acestep"):
    """
    场景一：输入歌词 + 一个音色 → 生成音乐

    流程:
    1. 选择一个已有音色（或生成新音色）
    2. 直接调用 /sing/generate 完成全部流程
    """
    print(f"\n{Colors.HEADER}{'='*60}{Colors.ENDC}")
    print(f"{Colors.BOLD}场景一：输入歌词 + 一个音色 → 生成音乐 (model: {model_type}){Colors.ENDC}")
    print(f"{Colors.HEADER}{'='*60}{Colors.ENDC}\n")

    # 示例歌词（生日快乐主题）
    test_lyrics = """[start]
[intro]
[00:05.00][verse]
窗外的风 停在了十月的黄昏
吹散了 书页间夹着的旧年轮
我们曾 在霓虹下奔跑得那么认真
以为青春 永远不会生根
[00:25.00][verse]
时钟在走 滴答声敲碎了天真
那些梦 像泡沫那样轻盈地沉
虽然生活 偶尔会下起无声的雨淋
但你的笑容 依然是唯一的安稳
[00:45.00][chorus]
亲爱的朋友 愿你岁岁平安无恙
哪怕世界 偶尔变得有些荒凉
在这特别的日子 请收下这束光
照亮你 心中最柔软的角落
[00:55.00][chorus]
祝你生日快乐 不止今天这一场
愿所有美好 都如期抵达身旁
无论走多远 回头还有我守望
这一份情谊 比岁月更长
[inst]
[01:10.00][verse]
烛光摇曳 映亮了疲惫的脸庞
许愿时刻 时间仿佛静止不动
不需要 多么宏大的誓言和梦想
只要你 能活得自在且从容
[01:25.00][chorus]
亲爱的朋友 愿你岁岁平安无恙
哪怕世界 偶尔变得有些荒凉
在这特别的日子 请收下这束光
照亮你 心中最柔软的角落
[01:35.00][chorus]
祝你生日快乐 不止今天这一场
愿所有美好 都如期抵达身旁
无论走多远 回头还有我守望
这一份情谊 比岁月更长
[01:50.00][end]"""

    # 检查是否有已有音色（ACE-Step 不使用音色参考，DiffRhythm 需要）
    voices = list_existing_voices()
    use_voice_path = (model_type == "diffrhythm" and voices)

    if use_voice_path:
        # DiffRhythm 模式：使用已有音色
        voice_info = voices[0]
        voice_path = voice_info["path"]
        voice_instructions = None
        log_info(f"DiffRhythm 模式：使用已有音色 {voice_info['filename']} (时长: {voice_info['duration']:.2f}s)")
    else:
        # ACE-Step 模式：不需要音色参考
        voice_path = None
        voice_instructions = "清澈甜美的女声"
        log_info("ACE-Step 模式：使用 voice_instructions 生成音色（音色仅用于后续 SoulX 转换）")

    # 调用 API
    log_info("调用 /sing/generate 接口...")

    payload = {
        "lyrics": test_lyrics,
        "style": "Pop, Happy",
        "duration": 90,
        "model_type": model_type
    }

    if use_voice_path:
        payload["voice_path"] = voice_path
    else:
        payload["voice_instructions"] = voice_instructions

    start_time = time.time()

    try:
        resp = requests.post(
            f"{API_BASE}/sing/generate",
            json=payload,
            timeout=600  # 10分钟超时
        )

        elapsed = time.time() - start_time

        if resp.status_code == 200:
            result = resp.json()
            log_success(f"生成完成！耗时: {elapsed:.1f}秒")
            print(f"\n{Colors.BOLD}结果:{Colors.ENDC}")
            print(f"  Song ID: {result['song_id']}")
            print(f"  歌曲: {result['song_path']}")
            print(f"  干声: {result['vocal_path']}")
            print(f"  音色: {result['voice_path']}")

            # 检查生成的文件
            song_duration = get_audio_duration(result['song_path'])
            vocal_duration = get_audio_duration(result['vocal_path'])
            log_success(f"歌曲时长: {song_duration:.1f}s, 干声时长: {vocal_duration:.1f}s")

            return True
        else:
            log_error(f"API 返回错误: {resp.status_code} - {resp.text}")
            return False

    except requests.exceptions.Timeout:
        log_error("请求超时（10分钟）")
        return False
    except Exception as e:
        log_error(f"请求失败: {e}")
        return False


def test_scenario_2_two_voices(model_type="acestep"):
    """
    场景二：输入歌词 + 两个音色（基础 + 替换）→ 生成音乐

    流程:
    1. 使用基础音色预生成歌曲（/sing/pregenerate）
    2. 使用替换音色进行实时转换（/sing/convert）
    """
    print(f"\n{Colors.HEADER}{'='*60}{Colors.ENDC}")
    print(f"{Colors.BOLD}场景二：输入歌词 + 两个音色（基础 + 替换）→ 生成音乐 (model: {model_type}){Colors.ENDC}")
    print(f"{Colors.HEADER}{'='*60}{Colors.ENDC}\n")

    # 示例歌词
    test_lyrics = """[start]
[intro]
[00:05.00][verse]
清晨的阳光轻轻洒在窗台上
新的一天开始了
希望今天也是美好的一天
充满温暖和快乐
[00:20.00][chorus]
让我们一起向前走
追逐心中的梦想
不管前方有多少困难
微笑面对每一天
[00:35.00][end]"""

    # 获取或创建两个不同音色
    voices = list_existing_voices()

    if len(voices) >= 2:
        base_voice = voices[0]
        replacement_voice = voices[1]
        log_info(f"使用已有音色 - 基础: {base_voice['filename']}, 替换: {replacement_voice['filename']}")
    elif len(voices) == 1:
        base_voice = voices[0]
        # 需要生成第二个音色
        log_info(f"已有1个音色，将生成第2个音色...")
        # 生成新音色（使用不同的描述）
        payload = {
            "voice_instructions": "温暖醇厚的男声",
            "voice_path": None
        }
        # 这里简化处理，实际应该调用 voice_designer
        replacement_voice = base_voice  # 暂时用同一个，实际应生成新的
        log_warning("简化处理：两个音色相同")
    else:
        log_info("没有已有音色，将使用 voice_instructions 生成两个音色...")
        # 生成两个不同的音色
        base_voice = {"path": None, "filename": "（将生成）"}
        replacement_voice = {"path": None, "filename": "（将生成）"}
        payload = {
            "voice_instructions": "清澈甜美的女声",
            "voice_path": None
        }

    # Step 1: 预生成歌曲
    log_info("Step 1: 预生成歌曲...")

    payload = {
        "lyrics": test_lyrics,
        "style": "Pop, Happy",
        "duration": 45,
        "model_type": model_type
    }

    # DiffRhythm 需要 voice_path 作为参考音色
    if model_type == "diffrhythm" and base_voice["path"]:
        payload["voice_path"] = base_voice["path"]
    elif model_type == "diffrhythm" and base_voice["path"] is None:
        # DiffRhythm 模式需要音色文件，简化为使用已有音色或跳过
        log_warning("DiffRhythm 模式需要音色文件，将使用已有音色（如有）")

    try:
        resp = requests.post(
            f"{API_BASE}/sing/pregenerate",
            json=payload,
            timeout=600
        )

        if resp.status_code != 200:
            log_error(f"预生成失败: {resp.status_code} - {resp.text}")
            return False

        pre_result = resp.json()
        song_id = pre_result["song_id"]
        log_success(f"预生成完成！Song ID: {song_id}")
        print(f"  歌曲: {pre_result['song_path']}")
        print(f"  干声: {pre_result['vocal_path']}")

    except Exception as e:
        log_error(f"预生成请求失败: {e}")
        return False

    # Step 2: 使用替换音色进行转换
    log_info("Step 2: 使用替换音色进行转换...")

    # 确定替换音色路径
    if len(voices) >= 2:
        replace_voice_path = replacement_voice["path"]
    elif len(voices) == 1:
        # 生成新的替换音色
        log_info("生成替换音色...")
        replace_voice_path = voices[0]["path"]  # 简化处理
    else:
        # 生成新音色
        replace_voice_path = None

    payload = {
        "song_id": song_id,
        "voice_path": replace_voice_path if replace_voice_path else "/data/voice-temp/voices/voice_new.wav"
    }

    if replace_voice_path is None:
        # 这里需要先生成音色...
        log_warning("需要先生成替换音色，简化处理使用基础音色")
        payload["voice_path"] = base_voice["path"] if base_voice["path"] else "/data/voice-temp/voices/voice_new.wav"

    start_time = time.time()

    try:
        resp = requests.post(
            f"{API_BASE}/sing/convert",
            json=payload,
            timeout=300
        )

        elapsed = time.time() - start_time

        if resp.status_code == 200:
            result = resp.json()
            log_success(f"音色转换完成！耗时: {elapsed:.1f}秒")
            print(f"\n{Colors.BOLD}最终结果:{Colors.ENDC}")
            print(f"  输出文件: {result['result_path']}")

            result_duration = get_audio_duration(result['result_path'])
            log_success(f"输出时长: {result_duration:.1f}s")

            return True
        else:
            log_error(f"转换失败: {resp.status_code} - {resp.text}")
            return False

    except Exception as e:
        log_error(f"转换请求失败: {e}")
        return False


def test_scenario_3_existing_music():
    """
    场景三：输入已有音乐文件 + 替换音色 → 生成音乐

    流程:
    1. 已有音乐文件路径
    2. 使用 vocal_separator 分离人声（或直接提供人声路径）
    3. 使用替换音色进行转换
    """
    print(f"\n{Colors.HEADER}{'='*60}{Colors.ENDC}")
    print(f"{Colors.BOLD}场景三：输入已有音乐文件 + 替换音色 → 生成音乐{Colors.ENDC}")
    print(f"{Colors.HEADER}{'='*60}{Colors.ENDC}\n")

    # 查找已有的预生成歌曲
    songs = list_existing_songs()

    if not songs:
        log_warning("没有预生成歌曲可供测试，请先运行场景一或场景二")
        return False

    # 使用第一个歌曲的干声
    target_song = songs[0]
    vocal_path = target_song["vocal_path"]
    song_id = target_song["song_id"]
    log_info(f"使用预生成歌曲: {song_id}")
    print(f"  干声路径: {vocal_path}")

    # 获取或创建替换音色
    voices = list_existing_voices()

    if voices:
        replacement_voice = voices[-1]  # 使用最后一个音色
        log_info(f"使用替换音色: {replacement_voice['filename']}")
        voice_path = replacement_voice["path"]
    else:
        log_warning("没有可用音色，请先生成音色")
        return False

    # 执行音色转换
    log_info("执行音色转换...")

    payload = {
        "song_id": song_id,
        "voice_path": voice_path
    }

    start_time = time.time()

    try:
        resp = requests.post(
            f"{API_BASE}/sing/convert",
            json=payload,
            timeout=300
        )

        elapsed = time.time() - start_time

        if resp.status_code == 200:
            result = resp.json()
            log_success(f"音色转换完成！耗时: {elapsed:.1f}秒")
            print(f"\n{Colors.BOLD}结果:{Colors.ENDC}")
            print(f"  输出文件: {result['result_path']}")

            result_duration = get_audio_duration(result['result_path'])
            log_success(f"输出时长: {result_duration:.1f}s")

            return True
        else:
            log_error(f"转换失败: {resp.status_code} - {resp.text}")
            return False

    except Exception as e:
        log_error(f"转换请求失败: {e}")
        return False


def list_resources():
    """列出可用资源"""
    print(f"\n{Colors.HEADER}{'='*60}{Colors.ENDC}")
    print(f"{Colors.BOLD}可用资源{Colors.ENDC}")
    print(f"{Colors.HEADER}{'='*60}{Colors.ENDC}\n")

    # 音色
    voices = list_existing_voices()
    print(f"{Colors.BOLD}音色文件 ({len(voices)} 个):{Colors.ENDC}")
    if voices:
        for v in voices:
            print(f"  - {v['filename']} ({v['duration']:.2f}s)")
    else:
        print("  （无）")

    # 歌曲
    songs = list_existing_songs()
    print(f"\n{Colors.BOLD}预生成歌曲 ({len(songs)} 个):{Colors.ENDC}")
    if songs:
        for s in songs:
            print(f"  - {s['song_id']}: {s['style']}, {s['duration']}s")
    else:
        print("  （无）")


def main():
    parser = argparse.ArgumentParser(description="Sing Agent 测试脚本")
    parser.add_argument(
        "--scenario",
        "-s",
        choices=["1", "2", "3", "all", "list"],
        default="list",
        help="测试场景: 1=单音色, 2=双音色, 3=已有音乐, all=全部, list=列出资源"
    )
    parser.add_argument(
        "--model",
        "-m",
        choices=["acestep", "diffrhythm"],
        default="acestep",
        help="生成模型: acestep（默认）或 diffrhythm"
    )
    parser.add_argument("--skip-health", action="store_true", help="跳过健康检查")

    args = parser.parse_args()

    if args.scenario == "list":
        list_resources()
        return

    if not args.skip_health:
        if not check_api_health():
            log_error("请确保 API 服务正在运行: python api_server.py")
            sys.exit(1)

    results = {}

    if args.scenario in ["1", "all"]:
        results[f"场景一({args.model})"] = test_scenario_1_one_voice(model_type=args.model)

    if args.scenario in ["2", "all"]:
        results[f"场景二({args.model})"] = test_scenario_2_two_voices(model_type=args.model)

    if args.scenario in ["3", "all"]:
        results["场景三"] = test_scenario_3_existing_music()

    # 总结
    print(f"\n{Colors.HEADER}{'='*60}{Colors.ENDC}")
    print(f"{Colors.BOLD}测试结果汇总{Colors.ENDC}")
    print(f"{Colors.HEADER}{'='*60}{Colors.ENDC}\n")

    for name, success in results.items():
        status = f"{Colors.OKGREEN}通过{Colors.ENDC}" if success else f"{Colors.FAIL}失败{Colors.ENDC}"
        print(f"  {name}: {status}")

    all_passed = all(results.values())
    if all_passed:
        log_success("\n所有测试通过！")
        sys.exit(0)
    else:
        log_error("\n部分测试失败")
        sys.exit(1)


if __name__ == "__main__":
    main()