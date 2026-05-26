# sing-agent 歌声克隆项目

## 项目目标
通过输入参考音色音频 + 歌词，生成具有该音色的歌曲。

## 架构流程
```
歌词 ──► DiffRhythm ──► AI歌曲 ──► 人声分离 ──► 干声
                                                    ▼
用户参考音色 ─────────────────────────────────► SoulX-Singer ──► 最终歌曲
                                                    ▲
                                                    │
                                              音色转换 (~10s)
```

## 服务地址

| 服务 | 地址 | 说明 |
|------|------|------|
| VoiceDesign (TTS) | `localhost:8020` | 生成参考音色 |
| DiffRhythm | `localhost:6000` | 歌词到歌曲 |
| SoulX-Singer | `localhost:7861` | 音色转换 |

## 快速开始

```python
import sys
sys.path.insert(0, "/data/script/voice/sing-agent/src")

from audio_prep import prepare_audio_for_soulx
from soulx_client import SoulXClient
from diffrhythm_client import DiffRhythmClient
import httpx

# 1. VoiceDesign 生成参考音色
response = httpx.post(
    "http://localhost:8020/v1/audio/speech",
    json={
        "model": "Qwen3-TTS-VoiceDesign",
        "input": "今天天气真不错",
        "task_type": "VoiceDesign",
        "instructions": "一个温柔甜美的女声",
        "response_format": "wav"
    },
    timeout=60
)
with open("/tmp/timbre.wav", "wb") as f:
    f.write(response.content)

# 2. 预处理音色
timbre_prepared = prepare_audio_for_soulx("/tmp/timbre.wav")

# 3. DiffRhythm 生成歌曲 (2-4分钟)
diff_client = DiffRhythmClient(api_url="http://localhost:6000")
song_path = diff_client.generate(
    lyrics="[start]\n[intro]\n测试\n[verse]\n新的一天\n",
    song_name="my_song",
    style="Pop, Happy",
    duration=30
)

# 4. SoulX-Singer 音色转换 (~10秒)
song_prepared = prepare_audio_for_soulx(song_path)
soulx_client = SoulXClient()
result = soulx_client.convert(
    prompt_audio=timbre_prepared,
    target_audio=song_prepared,
    pitch_shift=0,
    n_step=32
)

print(f"最终歌曲: {result}")
```

## 模块说明

### audio_prep.py - 音频预处理
```python
from audio_prep import prepare_audio_for_soulx, validate_audio_format

# 转换为 16kHz 单声道 WAV (SoulX-Singer 要求)
prepared = prepare_audio_for_soulx("/path/to/audio.wav")
# 返回: /tmp/soulx_input_xxx.wav

# 验证音频格式
is_valid, info = validate_audio_format("/path/to/audio.wav")
# info: {sample_rate, channels, duration, format, ...}
```

### soulx_client.py - SoulX-Singer 调用
```python
from soulx_client import SoulXClient, convert_vocal_timbre

# 使用类
client = SoulXClient()
result = client.convert(
    prompt_audio="/tmp/timbre.wav",   # 参考音色
    target_audio="/tmp/song.wav",      # 目标歌曲
    pitch_shift=0,                      # 音高偏移 (-36~36)
    n_step=32,                          # 采样步数 (1~200)
    cfg=1.0                             # CFG系数
)

# 或使用函数
result = convert_vocal_timbre(
    prompt_audio="/tmp/timbre.wav",
    target_audio="/tmp/song.wav"
)
```

### diffrhythm_client.py - DiffRhythm 调用
```python
from diffrhythm_client import DiffRhythmClient

client = DiffRhythmClient(api_url="http://localhost:6000")

# 检查状态
print(client.get_status())
# {'status': 'ok', 'model_loaded': True}

# 生成歌曲 (30秒约需2-4分钟)
song_path = client.generate(
    lyrics="[start]\n[intro]\n歌词\n[verse]\n内容\n",
    song_name="my_song",
    style="Pop, Happy",
    duration=30,     # 目标时长(秒)
    steps=16,        # 采样步数
    cfg_strength=2.0 # CFG强度
)
```

### vocal_separator.py - 人声分离
```python
from vocal_separator import separate_vocals, VocalSeparator

# 分离人声 (使用 Demucs)
vocal_path = separate_vocals("/path/to/song.wav")
# 返回: /tmp/separated/htdemucs/xxx/vocals.wav

# 或使用类
separator = VocalSeparator(output_dir="/tmp/separated")
vocal_path = separator.separate("/path/to/song.wav")
```

### orchestrator.py - 流水线整合
```python
from orchestrator import SingAgentOrchestrator, clone_song_with_timbre

# 使用 Orchestrator 类
orch = SingAgentOrchestrator()
song_path = orch.full_pipeline(
    lyrics="[verse]\n歌词\n",
    prompt_audio="/tmp/timbre.wav",
    style="Pop, Happy",
    duration=30
)

# 或使用便捷函数
result = clone_song_with_timbre(
    lyrics="[verse]\n歌词\n",
    prompt_audio="/tmp/timbre.wav"
)
```

## 性能基准

| 阶段 | 耗时 | 说明 |
|------|------|------|
| VoiceDesign | ~1s | 生成参考音色音频 |
| DiffRhythm | ~2-4分钟 | 生成30秒歌曲 (RTF 4-8x) |
| 人声分离 | ~5-10s | Demucs 分离 |
| SoulX-Singer | ~10s | 音色转换 |

**推荐架构**:
- 后台预生成 DiffRhythm 歌曲 + 人声分离
- 实时调用 SoulX-Singer 进行音色转换 (~10秒)

## 技术要点

1. **音频格式**: SoulX-Singer 要求 16kHz 单声道 WAV
2. **Gradio 6.x**: 必须使用 gradio_client 库，FileData 需要 meta 字段
3. **target_vocal_sep=False**: 避免 MDXNet 输出立体声导致 Whisper 报错
4. **预生成模式**: DiffRhythm 生成较慢，建议后台预生成

## 项目结构

```
/data/script/voice/sing-agent/
├── doc/
│   ├── PROJECT_PLAN.md    # 本文档
│   └── DESIGN.md          # 设计文档
├── src/
│   ├── __init__.py
│   ├── audio_prep.py      # 音频预处理 (16kHz mono)
│   ├── soulx_client.py    # SoulX-Singer 调用
│   ├── diffrhythm_client.py # DiffRhythm 调用
│   ├── vocal_separator.py # 人声分离 (Demucs)
│   └── orchestrator.py    # 流水线整合
├── tests/
│   ├── test_pipeline.py   # 基础测试
│   └── test_full_pipeline.py # 完整流水线测试
├── config/                # 配置文件
└── memory/                # 记忆文件
```

## 修复记录

| 日期 | 问题 | 解决方案 |
|------|------|----------|
| 2026-05-18 | SoulX-Singer torchcodec FFmpeg 兼容性问题 | 修改 audio_utils.py 使用 soundfile + scipy.signal.resample |
| 2026-05-18 | DiffRhythm API 返回空 body | 修改 diffrhythm_client.py 从容器获取最新文件 |
| 2026-05-19 | DiffRhythm 生成纯音乐没有人声 | 需要传入 ref_audio 参数提供人声参考音频 |
| 2026-05-19 | DiffRhythm 无法加载音频参考 | 容器缺少 torchcodec，运行 `pip install torchcodec` |

## 重要发现

### DiffRhythm 需要音频参考才能生成人声

**问题**: DiffRhythm 使用 text-style prompt 时只生成纯器乐，没有人声。

**解决方案**: 传入 `ref_audio` 参数提供一个带人声的参考音频：

```python
diff_client = DiffRhythmClient()
song_path = diff_client.generate(
    lyrics="[start]\n[intro]\n歌词\n[verse]\n内容\n",
    song_name="my_song",
    style="Pop, Happy",
    duration=30,
    ref_audio="/path/to/reference_vocal.wav"  # 重要：提供人声参考
)
```

**频率对比** (验证人声存在):
| 频率范围 | 无ref_audio | 有ref_audio |
|---------|-------------|-------------|
| 0-100 Hz | 80%+ | 16% |
| 100-300 Hz | 14% | 38% |
| 1000-3000 Hz | <1% | 14% |

### 必须安装 torchcodec

DiffRhythm 容器中需要安装 torchcodec 才能加载音频参考:
```bash
docker exec gpu2_diff_rhythm pip install torchcodec
```

```bash
# 检查容器状态
docker ps | grep -E "soulx|diff"

# 检查服务健康
curl -s http://localhost:6000/health
curl -s http://localhost:7861/ | head -3
```