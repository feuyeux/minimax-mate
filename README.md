# minimax-mate

一个面向 **MiniMax API** 的轻量命令行工具集合，目前包含两个脚本：

- `minimaxi-image-generate.py`：调用 `image-01` 生成图片并自动下载
- `minimaxi-speech-generate.py`：调用 `Speech 2.8` 进行文本转语音，并支持 `Voice Design`

---

## 1. 当前仓库文件

当前项目根目录里实际存在的核心文件：

| 文件 | 说明 |
| :-- | :-- |
| `README.md` | 使用说明 |
| `minimaxi-image-generate.py` | 文生图脚本 |
| `minimaxi-speech-generate.py` | 语音合成脚本 |
| `prompt.md` | 图片提示词示例 |
| `speech.txt` | 语音文本示例 |
| `pyproject.toml` | Python 项目配置 |
| `uv.lock` | 依赖锁文件 |

---

## 2. 环境准备

### 2.1 安装依赖

```bash
uv sync
```

### 2.2 配置 API Key

在项目根目录创建 `.env`：

```env
MINIMAX_API_KEY=你的 MiniMax API Key
```

两个脚本都会优先读取：

- 命令行参数 `--token`
- 环境变量 `MINIMAX_API_KEY`
- 当前目录中的 `.env`

---

## 3. 文生图

### 3.1 最小示例

```bash
uv run python minimaxi-image-generate.py \
  --prompt-file prompt.md \
  --aspect-ratio 16:9 \
  --out-dir generated-images
```

### 3.2 直接传提示词

```bash
uv run python minimaxi-image-generate.py \
  --prompt "电影级科技海报，两台旗舰笔记本在桌面上对峙" \
  --aspect-ratio 16:9 \
  --count 1
```

### 3.3 输出结果

执行成功后会自动创建 `generated-images/`，每次请求对应一个时间戳子目录，目录中通常包含：

- 图片文件，例如 `image_01.jpeg`
- `manifest.json`，用于记录请求体、接口响应和下载结果

---

## 4. 语音合成

### 4.1 直接使用已有音色

```bash
uv run python minimaxi-speech-generate.py \
  --text "你好，欢迎来到 MiniMax 语音合成示例。" \
  --voice-id English_Insightful_Speaker \
  --format mp3 \
  --out-dir generated-audio
```

### 4.2 从文件读取文本

```bash
uv run python minimaxi-speech-generate.py \
  --text-file speech.txt \
  --voice-id English_Insightful_Speaker \
  --format mp3 \
  --out-dir generated-audio
```

### 4.3 先做 Voice Design，再正式合成

```bash
uv run python minimaxi-speech-generate.py \
  --text-file speech.txt \
  --voice-prompt "温柔、冷静、富有科技感的中文女声，适合产品演示旁白。" \
  --preview-text "你好，这是这款声音的试听文本。" \
  --subtitle-enable \
  --out-dir generated-audio
```

### 4.4 输出结果

执行成功后会自动创建 `generated-audio/`，每次请求对应一个时间戳子目录，目录中可能包含：

- 正式音频文件，例如 `speech_audio.mp3`
- 试听音频，例如 `speech_voice_design_preview.mp3`
- 字幕文件
- `manifest.json`

## 5. 参考文档

- Speech T2A HTTP:
  - https://platform.minimaxi.com/docs/api-reference/speech-t2a-http
- Voice Design:
  - https://platform.minimaxi.com/docs/api-reference/voice-design-design
