# Sing Agent API 文档

## 概述

Sing Agent 是一个歌声合成系统，支持：
- 基于 Qwen3-TTS-VoiceDesign 的音色设计
- **基于 ACE-Step 的歌曲生成** (保留原始歌词)
- **基于 SoulX-Singer 的实时音色转换**
- **基于 Demucs 的人声分离**

## 基础信息

- **Base URL**: `http://localhost:8080`
- **存储路径**: `/data/voice-temp/` (跨容器共享)

### 目录结构
```
/data/voice-temp/
├── voices/     # 音色文件
├── lyrics/     # 歌词文件
├── songs/      # 预生成歌曲
└── output/     # 最终输出
```

### 音频参数

| 参数 | 值 | 说明 |
|------|-----|------|
| 采样率 | **24kHz** | SoulX-Singer 原生采样率，避免重采样 |
| 声道 | 1 (单声道) | 输入输出均为单声道 |
| 格式 | WAV | PCM_16 编码 |

**重要**: SoulX-Singer 内部使用 24kHz 采样率。使用原生 24kHz 可避免双重重采样导致的音质损失。

---

## API 端点

### 1. 健康检查

**GET** `/health`

检查服务是否正常运行。

**响应示例**:
```json
{
  "status": "ok"
}
```

---

### 2. 生成歌曲完整流程

**POST** `/sing/generate`

完整流程：音色设计 → 歌词生成 → 歌曲生成 → 人声分离 → SoulX 音色转换

**请求体**:
```json
{
  "voice_path": "/data/voice-temp/voices/voice_xxx.wav",  // 可选，音色文件路径
  "voice_instructions": "清澈甜美的女声",                  // 可选，音色描述（voice_path 为空时必填）
  "lyrics": "[start]\n[intro]\n...",                      // 可选，歌词（不传则用 theme 生成）
  "theme": "生日快乐",                                     // 可选，歌词主题
  "style": "Pop, Happy",                                  // 风格描述
  "duration": 90,                                         // 目标时长（秒），范围 30-180
  "pitch_shift": 0,                                       // 音高偏移（半音），范围 -12 到 12
  "model_type": "acestep"                                 // 生成模型: "acestep" 或 "diffrhythm"
}
```

**响应**:
```json
{
  "song_id": "song_12345",
  "song_path": "/data/voice-temp/songs/song_12345/song.wav",
  "vocal_path": "/data/voice-temp/songs/song_12345/vocal.wav",
  "voice_path": "/data/voice-temp/voices/voice_xxx.wav",
  "lyrics": "[start]\n[intro]\n[00:00.00][verse]\n...",
  "status": "completed"
}
```

**流程说明**:
1. 如果提供 `voice_path`，直接使用该音色文件
2. 如果只提供 `voice_instructions`，调用 Qwen3-TTS-VoiceDesign 生成音色
3. 如果提供 `lyrics`，直接使用；否则根据 `theme` 调用 Qwen3.6-35B 生成
4. 根据 `model_type` 选择生成模型：
   - **ACE-Step**: 不支持音频参考，使用文字风格描述
   - **DiffRhythm**: 使用音色作为参考音频
5. Demucs 分离人声
6. SoulX-Singer 将音色转换到人声

---

### 3. 预生成歌曲

**POST** `/sing/pregenerate`

只执行歌曲生成 + 人声分离，不做音色转换。

**请求体** (JSON):
```json
{
  "lyrics": "[start]\n[intro]\n[verse]\n清晨的阳光轻轻洒在窗台上\n...",
  "style": "Pop, Happy",
  "duration": 90,
  "voice_path": "/data/voice-temp/voices/voice_xxx.wav",
  "model_type": "acestep"
}
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| lyrics | string | 是 | 歌词（LRC 格式） |
| style | string | 否 | 风格描述，默认 "Pop, Happy" |
| duration | int | 否 | 目标时长，默认 90 秒 |
| voice_path | string | 否 | 参考音色文件路径（**仅 DiffRhythm 有效**） |
| model_type | string | 否 | 生成模型，默认 "acestep" |

**响应**:
```json
{
  "song_id": "pre_12345",
  "song_path": "/data/voice-temp/songs/pre_12345/song.wav",
  "vocal_path": "/data/voice-temp/songs/pre_12345/vocal.wav",
  "metadata_path": "/data/voice-temp/songs/pre_12345/metadata.json",
  "model_type": "acestep",
  "status": "ready"
}
```

---

### 4. 实时音色转换

**POST** `/sing/convert`

使用已预生成的歌曲干声 + 音色进行转换。

**请求体**:
```json
{
  "song_id": "pre_12345",
  "voice_path": "/data/voice-temp/voices/voice_xxx.wav"
}
```

**响应**:
```json
{
  "result_path": "/data/voice-temp/output/converted_12345.wav",
  "status": "completed"
}
```

---

### 5. 直接音色转换（已有歌曲 + 音色）

**POST** `/sing/convert-direct`

直接传入已有歌曲和参考音色，跳过人声分离和歌曲生成步骤。

**请求体**:
```json
{
  "song_path": "/data/voice-temp/songs/song_12345/vocal.wav", // 歌曲人声路径（从songs目录）
  "voice_path": "/data/voice-temp/voices/voice_xxx.wav",       // 参考音色路径
  "pitch_shift": 0,                                           // 音高偏移（半音），范围 -12 到 12
  "n_step": 32,                                               // 扩散步数，默认 32
  "cfg": 1.0                                                  // cfg 系数，默认 1.0（低值减少失真）
}
```

**响应**:
```json
{
  "result_path": "/data/voice-temp/output/converted_abc123.wav",
  "status": "completed"
}
```

**流程说明**:
1. 对两个音频进行预处理（24kHz 单声道）
2. SoulX-Singer 进行音色转换

**示例**:
```bash
curl -X POST http://localhost:8080/sing/convert-direct \
  -H "Content-Type: application/json" \
  -d '{
    "song_path": "/data/voice-temp/songs/song_12345/vocal.wav",
    "voice_path": "/data/voice-temp/voices/voice_xxx.wav",
    "pitch_shift": 0,
    "cfg": 1.0
  }'
```

---

### 6. 随机获取一首歌曲

**GET** `/sing/random-song`

从 `/data/voice-temp/songs/` 目录中随机返回一个已生成的歌曲路径。

**响应**:
```json
{
  "song_path": "/data/voice-temp/songs/song_12345/vocal.wav",
  "song_id": "song_12345"
}
```

**示例**:
```bash
curl -X GET http://localhost:8080/sing/random-song
```

---

### 7. 列出预生成歌曲

**GET** `/sing/songs`

**响应**:
```json
{
  "songs": [
    {
      "song_id": "song_12345",
      "lyrics": "...",
      "style": "Pop, Happy",
      "duration": 90,
      "model_type": "acestep",
      "song_path": "/data/voice-temp/songs/song_12345/song.wav",
      "vocal_path": "/data/voice-temp/songs/song_12345/vocal.wav",
      "status": "ready"
    }
  ]
}
```

---

### 8. 列出音色文件

**GET** `/sing/voices`

**响应**:
```json
{
  "voices": [
    {
      "filename": "voice_xxx.wav",
      "path": "/data/voice-temp/voices/voice_xxx.wav",
      "size": 156000
    }
  ]
}
```

---

## 使用场景

### 场景一：输入歌词 + 一个音色 → 生成音乐

```bash
# 使用 ACE-Step（默认）
curl -X POST http://localhost:8080/sing/generate \
  -H "Content-Type: application/json" \
  -d '{
    "voice_instructions": "清澈甜美的女声",
    "lyrics": "[start]\n[intro]\n[00:05.00][verse]\n窗外的风 停在了十月的黄昏\n...",
    "style": "Pop, Happy",
    "duration": 90,
    "model_type": "acestep"
  }'

# 使用 DiffRhythm（支持音频参考音色）
curl -X POST http://localhost:8080/sing/generate \
  -H "Content-Type: application/json" \
  -d '{
    "voice_path": "/data/voice-temp/voices/voice_8fe34d12.wav",
    "lyrics": "[start]\n[intro]\n[00:05.00][verse]\n窗外的风 停在了十月的黄昏\n...",
    "style": "Pop, Happy",
    "duration": 90,
    "model_type": "diffrhythm"
  }'
```

### 场景二：输入歌词 + 两个音色（基础 + 替换）→ 生成音乐

```bash
# Step 1: 预生成歌曲（使用 DiffRhythm + 基础音色）
curl -X POST http://localhost:8080/sing/pregenerate \
  -H "Content-Type: application/json" \
  -d '{
    "lyrics": "[start]\n[intro]\n[00:05.00][verse]\n窗外的风 停在了十月的黄昏\n...",
    "style": "Pop, Happy",
    "duration": 90,
    "voice_path": "/data/voice-temp/voices/voice_base.wav",
    "model_type": "diffrhythm"
  }'

# Step 2: 使用替换音色进行转换
curl -X POST http://localhost:8080/sing/convert \
  -H "Content-Type: application/json" \
  -d '{
    "song_id": "pre_12345",
    "voice_path": "/data/voice-temp/voices/voice_replacement.wav"
  }'
```

### 场景三：已有歌曲直接换音色

```bash
# 使用 /sing/convert-direct 直接转换（推荐）
curl -X POST http://localhost:8080/sing/convert-direct \
  -H "Content-Type: application/json" \
  -d '{
    "song_path": "/data/voice-temp/songs/song_12345/vocal.wav",
    "voice_path": "/data/voice-temp/voices/voice_replacement.wav",
    "cfg": 1.0
  }'
```

---

## 错误码

| 状态码 | 说明 |
|--------|------|
| 400 | 参数错误（如 voice_path 和 voice_instructions 同时为空，或 model_type 非法） |
| 404 | 资源不存在（如指定的 song_id 找不到） |
| 500 | 服务器内部错误 |

---

## 文件路径说明

所有文件路径均为**宿主机绝对路径**，系统会自动处理容器内路径映射：

| 宿主机路径 | 容器内路径 |
|-----------|-----------|
| `/data/voice-temp/voices/` | `/workspace/voices/` |
| `/data/voice-temp/lyrics/` | `/workspace/lyrics/` |
| `/data/voice-temp/songs/` | `/workspace/songs/` |
| `/data/voice-temp/output/` | `/workspace/output/` |
| `/data/DiffRhythm/output/` | `/workspace/output/` |

---

## 依赖服务

| 服务 | 地址 | Docker环境变量 | 说明 |
|------|------|---------------|------|
| SoulX-Singer | `http://localhost:7861` | `SOULX_URL` | 音色转换 |
| ACE-Step API | `http://localhost:8001` | `ACE_STEP_URL` | 歌曲生成 |
| VoiceDesign/TTS | `http://localhost:8020` | `TTS_URL` | 音色设计 |

**Docker 部署说明**:
- 容器内使用 `host.docker.internal` 访问宿主机服务
- 需要添加 `--add-host=host.docker.internal:host-gateway` 参数
- 或在 docker-compose.yml 中配置 `extra_hosts`

---

## 模型选择建议

| 场景 | 推荐模型 | 原因 |
|------|---------|------|
| 快速生成、保留原始歌词 | **ACE-Step** | 使用 `/release_task` 不重写歌词 |
| 需要精确人声特征控制 | **DiffRhythm** | 支持音频参考音色 |
| 已有音色文件，想保持一致性 | **DiffRhythm** | ref_audio 控制人声风格 |
| 纯文字风格描述 | **ACE-Step** | caption 描述风格 |