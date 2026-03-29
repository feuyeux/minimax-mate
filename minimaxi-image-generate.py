#!/usr/bin/env python3
"""
MiniMax 文生图 + 自动下载脚本。

默认读取环境变量:
  MINIMAX_API_KEY

示例:
  python3 minimaxi-image-generate.py \
    --prompt "电影级科技海报，两台旗舰笔记本在桌面上对峙" \
    --aspect-ratio 16:9 \
    --count 3 \
    --prompt-optimizer

  python3 minimaxi-image-generate.py \
    --prompt-file prompt.txt \
    --width 1536 \
    --height 864 \
    --out-dir ./generated-images
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
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


API_URL = "https://api.minimaxi.com/v1/image_generation"
DEFAULT_MODEL = "image-01"
SCRIPT_DIR = Path(__file__).resolve().parent


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
        description="调用 MiniMax 文生图接口并自动下载图片。",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            "常用方式:\n"
            "  1) 在 .env 中设置 MINIMAX_API_KEY='你的 token'\n"
            "  2) python3 minimaxi-image-generate.py --prompt 'A cinematic poster' --count 2\n\n"
            "也可以使用 --prompt-file 读取长提示词。"
        ),
    )
    prompt_group = parser.add_mutually_exclusive_group(required=True)
    prompt_group.add_argument("--prompt", help="直接传入提示词。")
    prompt_group.add_argument("--prompt-file", help="从文件读取提示词。")

    parser.add_argument("--token", help="MiniMax API Token；未传时读取环境变量，若未设置则尝试从 .env 加载 MINIMAX_API_KEY。")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"模型名，默认 {DEFAULT_MODEL}。")
    parser.add_argument("--aspect-ratio", help="宽高比，例如 1:1、16:9。")
    parser.add_argument("--width", type=int, help="生成宽度。与 --height 配对使用。")
    parser.add_argument("--height", type=int, help="生成高度。与 --width 配对使用。")
    parser.add_argument("--count", type=int, default=1, help="生成图片数量，对应接口字段 n。默认 1。")
    parser.add_argument(
        "--prompt-optimizer",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="是否启用提示词优化。默认开启，可用 --no-prompt-optimizer 关闭。",
    )
    parser.add_argument(
        "--download",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="是否自动下载返回的图片 URL。默认开启。",
    )
    parser.add_argument("--filename-prefix", default="image", help="下载图片文件名前缀，默认 image。")
    parser.add_argument("--out-dir", default="generated-images", help="输出目录，默认 ./generated-images。")
    parser.add_argument("--timeout", type=int, default=120, help="请求和下载超时时间（秒），默认 120。")
    parser.add_argument("--dry-run", action="store_true", help="只打印请求体，不发起真实请求。")
    return parser


def read_prompt(args: argparse.Namespace) -> str:
    if args.prompt:
        return args.prompt.strip()

    prompt_path = Path(args.prompt_file)
    if not prompt_path.is_file():
        raise FileNotFoundError(f"提示词文件不存在: {prompt_path}")

    content = prompt_path.read_text(encoding="utf-8").strip()
    if not content:
        raise ValueError(f"提示词文件为空: {prompt_path}")
    return content


def validate_args(args: argparse.Namespace) -> None:
    if args.count < 1:
        raise ValueError("--count 必须大于等于 1。")

    has_ratio = bool(args.aspect_ratio)
    has_size = args.width is not None or args.height is not None

    if has_size and (args.width is None or args.height is None):
        raise ValueError("--width 和 --height 必须同时传入。")

    if args.width is not None and args.width < 1:
        raise ValueError("--width 必须大于等于 1。")

    if args.height is not None and args.height < 1:
        raise ValueError("--height 必须大于等于 1。")

    if has_ratio and has_size:
        raise ValueError("--aspect-ratio 与 --width/--height 二选一，避免请求体歧义。")

    if not has_ratio and not has_size:
        raise ValueError("请提供 --aspect-ratio，或同时提供 --width 和 --height。")


def build_payload(args: argparse.Namespace, prompt: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": args.model,
        "prompt": prompt,
        "response_format": "url",
        "n": args.count,
        "prompt_optimizer": args.prompt_optimizer,
    }

    if args.aspect_ratio:
        payload["aspect_ratio"] = args.aspect_ratio
    else:
        payload["width"] = args.width
        payload["height"] = args.height

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


def ensure_success(response_json: dict[str, Any]) -> None:
    base_resp = response_json.get("base_resp") or {}
    status_code = base_resp.get("status_code", 0)
    if status_code != 0:
        raise RuntimeError(
            "MiniMax API 返回业务错误: "
            f"status_code={status_code}, status_msg={base_resp.get('status_msg')}, body={json.dumps(response_json, ensure_ascii=False)}"
        )


def detect_extension(url: str, content_type: str | None = None) -> str:
    parsed = urlparse(url)
    suffix = Path(parsed.path).suffix
    if suffix:
        return suffix

    if content_type:
        guessed = mimetypes.guess_extension(content_type.split(";")[0].strip())
        if guessed:
            return guessed

    return ".jpg"


def download_file(url: str, target_path: Path, timeout: int) -> Path:
    if requests is not None:
        with requests.get(url, stream=True, timeout=timeout) as response:
            try:
                response.raise_for_status()
            except requests.HTTPError as exc:
                raise RuntimeError(f"下载图片失败: HTTP {response.status_code}\n{response.text}") from exc
            content_type = response.headers.get("Content-Type")
            final_path = target_path.with_suffix(detect_extension(url, content_type))
            with final_path.open("wb") as output:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        output.write(chunk)
        return final_path

    request = Request(url, headers={"User-Agent": "python-urllib/3"})
    try:
        with urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get("Content-Type")
            final_path = target_path.with_suffix(detect_extension(url, content_type))
            with final_path.open("wb") as output:
                output.write(response.read())
            return final_path
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"下载图片失败: HTTP {exc.code}\n{error_body}") from exc
    except URLError as exc:
        raise RuntimeError(f"下载图片失败: {exc}") from exc


def create_run_dir(base_dir: str, request_id: str | None) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = request_id[:8] if request_id else "dryrun"
    run_dir = Path(base_dir) / f"{timestamp}-{suffix}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def save_manifest(run_dir: Path, manifest: dict[str, Any]) -> Path:
    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        load_dotenv_if_present()
        validate_args(args)
        prompt = read_prompt(args)
        payload = build_payload(args, prompt)

        if args.dry_run:
            print("=== DRY RUN ===")
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            print(f"output_dir={Path(args.out_dir).resolve()}")
            return 0

        token = args.token or os.getenv("MINIMAX_API_KEY")
        if not token:
            raise RuntimeError("缺少 API Token。请通过 --token 传入，或在环境变量 / .env 中设置 MINIMAX_API_KEY。")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }

        response_json = post_json(API_URL, headers, payload, timeout=args.timeout)
        ensure_success(response_json)

        request_id = response_json.get("id")
        run_dir = create_run_dir(args.out_dir, request_id)
        manifest = {
            "request": payload,
            "response": response_json,
            "downloads": [],
        }
        manifest_path = save_manifest(run_dir, manifest)

        image_urls = (response_json.get("data") or {}).get("image_urls") or []
        if not image_urls:
            raise RuntimeError(f"接口返回成功，但未找到 data.image_urls: {json.dumps(response_json, ensure_ascii=False)}")

        print(f"request_id={request_id}")
        print(f"manifest={manifest_path}")
        print("image_urls:")
        for image_url in image_urls:
            print(image_url)

        if args.download:
            for index, image_url in enumerate(image_urls, start=1):
                target_path = run_dir / f"{args.filename_prefix}_{index:02d}"
                final_path = download_file(image_url, target_path, timeout=args.timeout)
                manifest["downloads"].append(
                    {
                        "index": index,
                        "url": image_url,
                        "file": str(final_path),
                    }
                )
                print(f"downloaded={final_path}")
            manifest_path = save_manifest(run_dir, manifest)

        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
