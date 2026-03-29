# minimax-mate

**[Token Plan](https://platform.minimaxi.com/subscribe/token-plan)标准版**：

|                             | **Plus**           | **Max**               |
| :-------------------------- | :----------------- | :-------------------- |
| **M2.7**                    | 1,500 次请求/5小时 | 4,500 次请求/5小时    |
| **Speech 2.8**              | 4,000 字符/日      | 11,000 字符/日        |
| **image-01**                | 50 张/日           | 120 张/日             |
| **Hailuo-2.3-Fast 768P 6s** | —                  | 2 个/日               |
| **Hailuo-2.3 768P 6s**      | —                  | 2 个/日               |
| **Music-2.5**               | —                  | 4 首/日（每首≤5分钟） |

## How to use

### MiniMax 文生图 Image 01

```bash
uv sync
```

```env
MINIMAX_API_KEY=你的 MiniMax API Key
```

```bash
uv run python minimaxi-image-generate.py \
  --prompt-file prompt.md \
  --aspect-ratio 16:9 \
  --out-dir generated-images
```

### MiniMax 语音 Speech 2.8

```bash
uv run python minimaxi-speech-generate.py \
  --text "你好，欢迎来到 MiniMax 语音合成示例。" \
  --voice-id English_Insightful_Speaker \
  --format mp3 \
  --out-dir generated-audio
```

使用音色设计后再合成:

```bash
uv run python minimaxi-speech-generate.py \
  --text-file speech.txt \
  --voice-prompt "温柔、冷静、富有科技感的中文女声，适合产品演示旁白。" \
  --preview-text "你好，这是这款声音的试听文本。" \
  --subtitle-enable \
  --out-dir generated-audio
```
