#!/usr/bin/env python3
"""
MiniMax 语音合成 + 可选音色设计 + 自动保存脚本。

默认读取环境变量:
  MINIMAX_API_KEY

示例:
  python3 minimaxi-speech-generate.py \
    --text "你好，欢迎来到 MiniMax 语音合成示例。" \
    --voice-id English_Insightful_Speaker \
    --format mp3 \
    --out-dir ./generated-audio

  python3 minimaxi-speech-generate.py \
    --text-file speech.txt \
    --voice-prompt "温柔、冷静、富有科技感的中文女声，适合产品演示旁白。" \
    --preview-text "你好，这是这款声音的试听文本。" \
    --subtitle-enable
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

try:
    import requests  # type: ignore
except ImportError:
    requests = None


DEFAULT_API_BASE_URL = "https://api.minimaxi.com"
DEFAULT_MODEL = "speech-2.8-hd"
DEFAULT_VOICE_ID = "male-qn-qingse"
SCRIPT_DIR = Path(__file__).resolve().parent
T2A_PATH = "/v1/t2a_v2"
VOICE_DESIGN_PATH = "/v1/voice_design"
TEXT_MAX_LENGTH = 10000
PREVIEW_TEXT_MAX_LENGTH = 500
VALID_MODELS = [
    "speech-2.8-hd",
    "speech-2.8-turbo",
    "speech-2.6-hd",
    "speech-2.6-turbo",
    "speech-02-hd",
    "speech-02-turbo",
    "speech-01-hd",
    "speech-01-turbo",
]
VALID_EMOTIONS = [
    "happy",
    "sad",
    "angry",
    "fearful",
    "disgusted",
    "surprised",
    "calm",
    "fluent",
    "whisper",
]
VALID_SAMPLE_RATES = [8000, 16000, 22050, 24000, 32000, 44100]
VALID_BITRATES = [32000, 64000, 128000, 256000]
VALID_AUDIO_FORMATS = ["mp3", "pcm", "flac", "wav"]
VALID_CHANNELS = [1, 2]
VALID_LANGUAGE_BOOSTS = [
    "Chinese",
    "Chinese,Yue",
    "English",
    "Arabic",
    "Russian",
    "Spanish",
    "French",
    "Portuguese",
    "German",
    "Turkish",
    "Dutch",
    "Ukrainian",
    "Vietnamese",
    "Indonesian",
    "Japanese",
    "Italian",
    "Korean",
    "Thai",
    "Polish",
    "Romanian",
    "Greek",
    "Czech",
    "Finnish",
    "Hindi",
    "Bulgarian",
    "Danish",
    "Hebrew",
    "Malay",
    "Persian",
    "Slovak",
    "Swedish",
    "Croatian",
    "Filipino",
    "Hungarian",
    "Norwegian",
    "Slovenian",
    "Catalan",
    "Nynorsk",
    "Tamil",
    "Afrikaans",
    "auto",
]
VALID_SOUND_EFFECTS = [
    "spacious_echo",
    "auditorium_echo",
    "lofi_telephone",
    "robotic",
]


def parse_dotenv_line(raw_line: str) -> tuple[str, str] | None:
    line = raw_line.strip()
    if not line or line.startswith("#"):
        return None

    if line.startswith("export "):
        line = line[len("export ") :].strip()

    if "=" not in line:
        return None

    key, value = line.split("=", 1)
    key = key.strip()
    value = value.strip()
    if not key:
        return None

    if value and value[0] in {"'", '"'} and value[-1:] == value[0]:
        value = value[1:-1]
    elif " #" in value:
        value = value.split(" #", 1)[0].rstrip()

    return key, value


def load_dotenv_if_present() -> None:
    candidate_paths = [Path.cwd() / ".env", SCRIPT_DIR / ".env"]
    seen_paths: set[Path] = set()

    for env_path in candidate_paths:
        resolved_path = env_path.resolve()
        if resolved_path in seen_paths or not resolved_path.is_file():
            continue

        seen_paths.add(resolved_path)
        for raw_line in resolved_path.read_text(encoding="utf-8").splitlines():
            parsed = parse_dotenv_line(raw_line)
            if parsed is None:
                continue

            key, value = parsed
            os.environ.setdefault(key, value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="调用 MiniMax 同步语音合成接口，并可选先进行音色设计。",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            "常用方式:\n"
            "  1) 在 .env 中设置 MINIMAX_API_KEY='你的 token'\n"
            "  2) python3 minimaxi-speech-generate.py --text '你好' --voice-id English_Insightful_Speaker\n"
            "  3) python3 minimaxi-speech-generate.py --text-file speech.txt --voice-prompt '知性中文女声' --preview-text '试听文本'\n"
        ),
    )

    text_group = parser.add_mutually_exclusive_group(required=True)
    text_group.add_argument("--text", help="直接传入要合成的文本。")
    text_group.add_argument("--text-file", help="从文件读取要合成的文本。")

    preview_group = parser.add_mutually_exclusive_group()
    preview_group.add_argument("--preview-text", help="音色设计接口使用的试听文本。")
    preview_group.add_argument("--preview-text-file", help="从文件读取音色设计接口使用的试听文本。")

    parser.add_argument("--token", help="MiniMax API Token；未传时读取环境变量，若未设置则尝试从 .env 加载 MINIMAX_API_KEY。")
    parser.add_argument(
        "--api-base-url",
        default=DEFAULT_API_BASE_URL,
        help=(
            "API Base URL，默认 https://api.minimaxi.com 。"
            "如需使用文档中的北京备用地址，可传 https://api-bj.minimaxi.com"
        ),
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, choices=VALID_MODELS, help=f"模型名，默认 {DEFAULT_MODEL}。")
    parser.add_argument(
        "--voice-id",
        help=f"合成使用的 voice_id。若未传且未启用音色设计/混音，则默认使用 {DEFAULT_VOICE_ID}。",
    )
    parser.add_argument("--voice-prompt", help="音色设计描述；传入后会先调用 /v1/voice_design 生成 voice_id。")
    parser.add_argument("--designed-voice-id", help="调用音色设计接口时使用的自定义 voice_id。")
    parser.add_argument("--speed", type=float, help="语速，范围 [0.5, 2]。")
    parser.add_argument("--vol", type=float, help="音量，范围 (0, 10]。")
    parser.add_argument("--pitch", type=int, help="音调，范围 [-12, 12]。")
    parser.add_argument("--emotion", choices=VALID_EMOTIONS, help="情绪控制。")
    parser.add_argument(
        "--text-normalization",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="是否启用中英文文本规范化；默认不显式传参。",
    )
    parser.add_argument(
        "--latex-read",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="是否朗读 LaTeX 公式；默认不显式传参。",
    )
    parser.add_argument("--sample-rate", type=int, choices=VALID_SAMPLE_RATES, help="采样率。")
    parser.add_argument("--bitrate", type=int, choices=VALID_BITRATES, help="比特率，仅 mp3 有效。")
    parser.add_argument(
        "--format",
        dest="audio_format",
        choices=VALID_AUDIO_FORMATS,
        default="mp3",
        help="输出音频格式，默认 mp3。",
    )
    parser.add_argument("--channel", type=int, choices=VALID_CHANNELS, help="声道数。")
    parser.add_argument(
        "--tone",
        action="append",
        default=[],
        help="发音字典条目，可重复传入，例如 --tone '处理/(chu3)(li3)'。",
    )
    parser.add_argument(
        "--timbre-weight",
        action="append",
        default=[],
        help="混音音色，格式 voice_id=weight，可重复传入，最多 4 项。",
    )
    parser.add_argument("--language-boost", choices=VALID_LANGUAGE_BOOSTS, help="增强指定语言/方言的识别能力。")
    parser.add_argument("--voice-effect-pitch", type=int, help="声音效果器 pitch，范围 [-100, 100]。")
    parser.add_argument("--voice-effect-intensity", type=int, help="声音效果器 intensity，范围 [-100, 100]。")
    parser.add_argument("--voice-effect-timbre", type=int, help="声音效果器 timbre，范围 [-100, 100]。")
    parser.add_argument("--voice-sound-effect", choices=VALID_SOUND_EFFECTS, help="声音效果器 sound_effects。")
    parser.add_argument(
        "--subtitle-enable",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="是否开启字幕服务。默认关闭。",
    )
    parser.add_argument(
        "--output-format",
        choices=["url", "hex"],
        default="hex",
        help="控制接口返回 url 还是 hex，默认 hex。",
    )
    parser.add_argument(
        "--aigc-watermark",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="是否在音频末尾添加 AIGC 水印。默认关闭。",
    )
    parser.add_argument(
        "--download",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="是否自动保存返回的音频/字幕/试听音频。默认开启。",
    )
    parser.add_argument("--filename-prefix", default="speech", help="输出文件名前缀，默认 speech。")
    parser.add_argument("--out-dir", default="generated-audio", help="输出目录，默认 ./generated-audio。")
    parser.add_argument("--timeout", type=int, default=120, help="请求和下载超时时间（秒），默认 120。")
    parser.add_argument("--dry-run", action="store_true", help="只打印请求体，不发起真实请求。")
    return parser


def read_text_value(direct_value: str | None, file_path: str | None, label: str) -> str:
    if direct_value:
        value = direct_value.strip()
        if value:
            return value
        raise ValueError(f"{label}不能为空。")

    if not file_path:
        raise ValueError(f"缺少 {label}。")

    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"{label}文件不存在: {path}")

    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise ValueError(f"{label}文件为空: {path}")
    return value


def parse_timbre_weights(raw_values: list[str]) -> list[dict[str, int]]:
    weights: list[dict[str, int]] = []
    for raw_value in raw_values:
        if "=" not in raw_value:
            raise ValueError(f"--timbre-weight 格式错误，应为 voice_id=weight: {raw_value}")

        voice_id, raw_weight = raw_value.split("=", 1)
        voice_id = voice_id.strip()
        raw_weight = raw_weight.strip()
        if not voice_id or not raw_weight:
            raise ValueError(f"--timbre-weight 格式错误，应为 voice_id=weight: {raw_value}")

        try:
            weight = int(raw_weight)
        except ValueError as exc:
            raise ValueError(f"--timbre-weight 的 weight 必须是整数: {raw_value}") from exc

        if not 1 <= weight <= 100:
            raise ValueError(f"--timbre-weight 的 weight 必须在 [1, 100] 内: {raw_value}")

        weights.append({"voice_id": voice_id, "weight": weight})

    if len(weights) > 4:
        raise ValueError("timbre_weights 最多支持 4 个音色。")

    return weights


def validate_args(args: argparse.Namespace, text: str, preview_text: str | None, timbre_weights: list[dict[str, int]]) -> None:
    if len(text) > TEXT_MAX_LENGTH:
        raise ValueError(f"合成文本长度不能超过 {TEXT_MAX_LENGTH} 字符。")

    if preview_text is not None and len(preview_text) > PREVIEW_TEXT_MAX_LENGTH:
        raise ValueError(f"试听文本长度不能超过 {PREVIEW_TEXT_MAX_LENGTH} 字符。")

    if args.voice_prompt and preview_text is None:
        raise ValueError("启用 --voice-prompt 时，必须提供 --preview-text 或 --preview-text-file。")

    if preview_text is not None and not args.voice_prompt:
        raise ValueError("--preview-text / --preview-text-file 仅在启用 --voice-prompt 时使用。")

    if args.designed_voice_id and not args.voice_prompt:
        raise ValueError("--designed-voice-id 仅在启用 --voice-prompt 时使用。")

    if args.voice_id and timbre_weights:
        raise ValueError("使用 --timbre-weight 进行混音时，请不要同时传入 --voice-id。")

    if args.voice_prompt and timbre_weights:
        raise ValueError("当前脚本暂不支持“音色设计 + timbre_weights 混音”同时使用。")

    if args.speed is not None and not 0.5 <= args.speed <= 2:
        raise ValueError("--speed 必须在 [0.5, 2] 内。")

    if args.vol is not None and not 0 < args.vol <= 10:
        raise ValueError("--vol 必须在 (0, 10] 内。")

    if args.pitch is not None and not -12 <= args.pitch <= 12:
        raise ValueError("--pitch 必须在 [-12, 12] 内。")

    if args.voice_effect_pitch is not None and not -100 <= args.voice_effect_pitch <= 100:
        raise ValueError("--voice-effect-pitch 必须在 [-100, 100] 内。")

    if args.voice_effect_intensity is not None and not -100 <= args.voice_effect_intensity <= 100:
        raise ValueError("--voice-effect-intensity 必须在 [-100, 100] 内。")

    if args.voice_effect_timbre is not None and not -100 <= args.voice_effect_timbre <= 100:
        raise ValueError("--voice-effect-timbre 必须在 [-100, 100] 内。")

    if args.bitrate is not None and args.audio_format != "mp3":
        raise ValueError("--bitrate 仅在 --format mp3 时有效。")

    if args.audio_format == "pcm" and (
        args.voice_effect_pitch is not None
        or args.voice_effect_intensity is not None
        or args.voice_effect_timbre is not None
        or args.voice_sound_effect is not None
    ):
        raise ValueError("voice_modify 仅支持非流式 mp3/wav/flac；当前 --format pcm 不支持。")

    if args.emotion in {"fluent", "whisper"} and args.model not in {"speech-2.6-hd", "speech-2.6-turbo"}:
        raise ValueError("emotion=fluent/whisper 仅对 speech-2.6-hd 与 speech-2.6-turbo 有效。")

    if args.timeout < 1:
        raise ValueError("--timeout 必须大于等于 1。")


def build_voice_design_payload(args: argparse.Namespace, preview_text: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "prompt": args.voice_prompt,
        "preview_text": preview_text,
    }
    if args.designed_voice_id:
        payload["voice_id"] = args.designed_voice_id
    if args.aigc_watermark:
        payload["aigc_watermark"] = True
    return payload


def build_voice_modify(args: argparse.Namespace) -> dict[str, Any] | None:
    payload: dict[str, Any] = {}
    if args.voice_effect_pitch is not None:
        payload["pitch"] = args.voice_effect_pitch
    if args.voice_effect_intensity is not None:
        payload["intensity"] = args.voice_effect_intensity
    if args.voice_effect_timbre is not None:
        payload["timbre"] = args.voice_effect_timbre
    if args.voice_sound_effect is not None:
        payload["sound_effects"] = args.voice_sound_effect
    return payload or None


def build_voice_setting(args: argparse.Namespace, resolved_voice_id: str, timbre_weights: list[dict[str, int]]) -> dict[str, Any]:
    voice_setting: dict[str, Any] = {"voice_id": "" if timbre_weights else resolved_voice_id}
    if args.speed is not None:
        voice_setting["speed"] = args.speed
    if args.vol is not None:
        voice_setting["vol"] = args.vol
    if args.pitch is not None:
        voice_setting["pitch"] = args.pitch
    if args.emotion is not None:
        voice_setting["emotion"] = args.emotion
    if args.text_normalization is not None:
        voice_setting["text_normalization"] = args.text_normalization
    if args.latex_read is not None:
        voice_setting["latex_read"] = args.latex_read
    return voice_setting


def build_audio_setting(args: argparse.Namespace) -> dict[str, Any]:
    audio_setting: dict[str, Any] = {"format": args.audio_format}
    if args.sample_rate is not None:
        audio_setting["sample_rate"] = args.sample_rate
    if args.bitrate is not None:
        audio_setting["bitrate"] = args.bitrate
    if args.channel is not None:
        audio_setting["channel"] = args.channel
    return audio_setting


def build_t2a_payload(
    args: argparse.Namespace,
    text: str,
    resolved_voice_id: str,
    timbre_weights: list[dict[str, int]],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": args.model,
        "text": text,
        "stream": False,
        "voice_setting": build_voice_setting(args, resolved_voice_id, timbre_weights),
        "audio_setting": build_audio_setting(args),
        "subtitle_enable": args.subtitle_enable,
        "output_format": args.output_format,
        "aigc_watermark": args.aigc_watermark,
    }

    if args.tone:
        payload["pronunciation_dict"] = {"tone": args.tone}

    if timbre_weights:
        payload["timbre_weights"] = timbre_weights

    language_boost = "Chinese" if args.latex_read else args.language_boost
    if language_boost is not None:
        payload["language_boost"] = language_boost

    voice_modify = build_voice_modify(args)
    if voice_modify is not None:
        payload["voice_modify"] = voice_modify

    return payload


def post_json(url: str, headers: dict[str, str], payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    if requests is not None:
        response = requests.post(url, json=payload, headers=headers, timeout=timeout)
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"MiniMax API 请求失败: HTTP {response.status_code}\n{response.text}") from exc
        return response.json()

    body = json.dumps(payload).encode("utf-8")
    request = Request(url, data=body, headers=headers, method="POST")

    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"MiniMax API 请求失败: HTTP {exc.code}\n{error_body}") from exc
    except URLError as exc:
        raise RuntimeError(f"MiniMax API 请求失败: {exc}") from exc


def ensure_success(response_json: dict[str, Any], label: str) -> None:
    base_resp = response_json.get("base_resp") or {}
    status_code = base_resp.get("status_code", 0)
    if status_code != 0:
        raise RuntimeError(
            f"MiniMax API 返回业务错误（{label}）: "
            f"status_code={status_code}, status_msg={base_resp.get('status_msg')}, "
            f"body={json.dumps(response_json, ensure_ascii=False)}"
        )


def looks_like_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def normalize_hex_string(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith("0x"):
        stripped = stripped[2:]
    return re.sub(r"\s+", "", stripped)


def decode_hex_bytes(value: str) -> bytes:
    normalized = normalize_hex_string(value)
    try:
        return bytes.fromhex(normalized)
    except ValueError as exc:
        raise RuntimeError("接口返回的 hex 数据无法解码。") from exc


def extension_from_audio_format(audio_format: str | None) -> str | None:
    if audio_format is None:
        return None
    mapping = {
        "mp3": ".mp3",
        "wav": ".wav",
        "flac": ".flac",
        "pcm": ".pcm",
        "json": ".json",
    }
    return mapping.get(audio_format)


def detect_extension(url: str, content_type: str | None = None, preferred_extension: str | None = None) -> str:
    parsed = urlparse(url)
    suffix = Path(parsed.path).suffix
    if suffix:
        return suffix

    if content_type:
        guessed = mimetypes.guess_extension(content_type.split(";", 1)[0].strip())
        if guessed:
            return guessed

    if preferred_extension:
        return preferred_extension

    return ".bin"


def detect_audio_extension_from_bytes(data: bytes, preferred_extension: str | None = None) -> str:
    if len(data) >= 3 and data[:3] == b"ID3":
        return ".mp3"
    if len(data) >= 2 and data[:2] in {
        b"\xff\xfb",
        b"\xff\xf3",
        b"\xff\xf2",
    }:
        return ".mp3"
    if len(data) >= 4 and data[:4] == b"fLaC":
        return ".flac"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return ".wav"
    if preferred_extension:
        return preferred_extension
    return ".bin"


def download_file(url: str, target_path: Path, timeout: int, preferred_extension: str | None = None) -> Path:
    if requests is not None:
        with requests.get(url, stream=True, timeout=timeout) as response:
            try:
                response.raise_for_status()
            except requests.HTTPError as exc:
                raise RuntimeError(f"下载文件失败: HTTP {response.status_code}\n{response.text}") from exc
            content_type = response.headers.get("Content-Type")
            final_path = target_path.with_suffix(detect_extension(url, content_type, preferred_extension))
            with final_path.open("wb") as output:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        output.write(chunk)
        return final_path

    request = Request(url, headers={"User-Agent": "python-urllib/3"})
    try:
        with urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get("Content-Type")
            final_path = target_path.with_suffix(detect_extension(url, content_type, preferred_extension))
            with final_path.open("wb") as output:
                output.write(response.read())
            return final_path
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"下载文件失败: HTTP {exc.code}\n{error_body}") from exc
    except URLError as exc:
        raise RuntimeError(f"下载文件失败: {exc}") from exc


def save_binary_blob(data: bytes, target_path: Path, preferred_extension: str | None = None) -> Path:
    final_path = target_path.with_suffix(detect_audio_extension_from_bytes(data, preferred_extension))
    final_path.write_bytes(data)
    return final_path


def sanitize_run_suffix(identifier: str | None) -> str:
    if not identifier:
        return "run"
    sanitized = re.sub(r"[^A-Za-z0-9_-]+", "", identifier)
    return sanitized[:16] or "run"


def create_run_dir(base_dir: str, identifier: str | None) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = sanitize_run_suffix(identifier)
    run_dir = Path(base_dir) / f"{timestamp}-{suffix}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def save_manifest(run_dir: Path, manifest: dict[str, Any]) -> Path:
    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path


def resolve_audio_value(response_json: dict[str, Any]) -> str | None:
    data = response_json.get("data") or {}
    return data.get("audio") or data.get("audio_file")


def resolve_subtitle_value(response_json: dict[str, Any]) -> str | None:
    data = response_json.get("data") or {}
    return data.get("subtitle_file")


def save_audio_artifact(
    audio_value: str,
    target_path: Path,
    timeout: int,
    preferred_format: str | None,
) -> dict[str, Any]:
    preferred_extension = extension_from_audio_format(preferred_format)
    if looks_like_url(audio_value):
        final_path = download_file(audio_value, target_path, timeout, preferred_extension)
        return {
            "kind": "audio",
            "source": "url",
            "url": audio_value,
            "file": str(final_path),
        }

    audio_bytes = decode_hex_bytes(audio_value)
    final_path = save_binary_blob(audio_bytes, target_path, preferred_extension)
    return {
        "kind": "audio",
        "source": "hex",
        "file": str(final_path),
        "bytes": len(audio_bytes),
    }


def save_subtitle_artifact(subtitle_value: str, target_path: Path, timeout: int) -> dict[str, Any]:
    if looks_like_url(subtitle_value):
        final_path = download_file(subtitle_value, target_path, timeout, ".json")
        return {
            "kind": "subtitle",
            "source": "url",
            "url": subtitle_value,
            "file": str(final_path),
        }

    final_path = target_path.with_suffix(".json")
    final_path.write_text(subtitle_value, encoding="utf-8")
    return {
        "kind": "subtitle",
        "source": "inline",
        "file": str(final_path),
    }


def resolve_token(args: argparse.Namespace) -> str:
    token = args.token or os.getenv("MINIMAX_API_KEY")
    if not token:
        raise RuntimeError("缺少 API Token。请通过 --token 传入，或在环境变量 / .env 中设置 MINIMAX_API_KEY。")
    return token


def make_api_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}{path}"


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    run_dir: Path | None = None
    manifest: dict[str, Any] = {"artifacts": []}

    try:
        load_dotenv_if_present()
        text = read_text_value(args.text, args.text_file, "合成文本")
        preview_text = None
        if args.voice_prompt or args.preview_text or args.preview_text_file:
            preview_text = read_text_value(args.preview_text, args.preview_text_file, "试听文本")

        timbre_weights = parse_timbre_weights(args.timbre_weight)
        validate_args(args, text, preview_text, timbre_weights)

        designed_voice_payload: dict[str, Any] | None = None
        designed_voice_response: dict[str, Any] | None = None
        resolved_voice_id = args.voice_id or DEFAULT_VOICE_ID

        if args.voice_prompt:
            assert preview_text is not None
            designed_voice_payload = build_voice_design_payload(args, preview_text)
            resolved_voice_id = args.designed_voice_id or "<voice_design_voice_id>"

        t2a_payload = build_t2a_payload(args, text, resolved_voice_id, timbre_weights)

        if args.dry_run:
            dry_run_payload: dict[str, Any] = {"speech_request": t2a_payload}
            if designed_voice_payload is not None:
                dry_run_payload["voice_design_request"] = designed_voice_payload
            print("=== DRY RUN ===")
            print(json.dumps(dry_run_payload, ensure_ascii=False, indent=2))
            print(f"output_dir={Path(args.out_dir).resolve()}")
            return 0

        token = resolve_token(args)
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }

        if designed_voice_payload is not None:
            voice_design_url = make_api_url(args.api_base_url, VOICE_DESIGN_PATH)
            designed_voice_response = post_json(voice_design_url, headers, designed_voice_payload, timeout=args.timeout)
            ensure_success(designed_voice_response, "voice_design")
            resolved_voice_id = designed_voice_response.get("voice_id") or args.designed_voice_id
            if not resolved_voice_id:
                raise RuntimeError(f"音色设计成功，但返回中缺少 voice_id: {json.dumps(designed_voice_response, ensure_ascii=False)}")

            run_dir = create_run_dir(args.out_dir, resolved_voice_id)
            manifest["voice_design_request"] = designed_voice_payload
            manifest["voice_design_response"] = designed_voice_response

            if args.download:
                trial_audio = designed_voice_response.get("trial_audio")
                if trial_audio:
                    artifact = save_audio_artifact(
                        trial_audio,
                        run_dir / f"{args.filename_prefix}_voice_design_preview",
                        timeout=args.timeout,
                        preferred_format=None,
                    )
                    manifest["artifacts"].append(artifact)

            t2a_payload = build_t2a_payload(args, text, resolved_voice_id, timbre_weights)

        t2a_url = make_api_url(args.api_base_url, T2A_PATH)
        t2a_response = post_json(t2a_url, headers, t2a_payload, timeout=args.timeout)
        ensure_success(t2a_response, "t2a_v2")

        if run_dir is None:
            run_dir = create_run_dir(args.out_dir, t2a_response.get("trace_id"))

        manifest["speech_request"] = t2a_payload
        manifest["speech_response"] = t2a_response

        audio_value = resolve_audio_value(t2a_response)
        if not audio_value:
            raise RuntimeError(f"接口返回成功，但未找到 data.audio: {json.dumps(t2a_response, ensure_ascii=False)}")

        if args.download:
            artifact = save_audio_artifact(
                audio_value,
                run_dir / f"{args.filename_prefix}_audio",
                timeout=args.timeout,
                preferred_format=args.audio_format,
            )
            manifest["artifacts"].append(artifact)

            subtitle_value = resolve_subtitle_value(t2a_response)
            if subtitle_value:
                artifact = save_subtitle_artifact(
                    subtitle_value,
                    run_dir / f"{args.filename_prefix}_subtitle",
                    timeout=args.timeout,
                )
                manifest["artifacts"].append(artifact)

        manifest_path = save_manifest(run_dir, manifest)
        print(f"trace_id={t2a_response.get('trace_id')}")
        print(f"voice_id={resolved_voice_id}")
        print(f"manifest={manifest_path}")
        print(f"audio={audio_value[:200] if looks_like_url(audio_value) else f'<hex:{len(normalize_hex_string(audio_value))} chars>'}")
        subtitle_value = resolve_subtitle_value(t2a_response)
        if subtitle_value:
            print(f"subtitle={subtitle_value}")
        for artifact in manifest["artifacts"]:
            if artifact.get("file"):
                print(f"saved={artifact['file']}")

        return 0
    except Exception as exc:
        if run_dir is not None:
            manifest["error"] = str(exc)
            try:
                save_manifest(run_dir, manifest)
            except Exception:
                pass
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
