#!/usr/bin/env python3
"""
gemini_gen.py — Gemini image generation/editing via OpenAI-compatible API.

Reads config from ~/.claude/gemini_image_config.json.
Called by cad_pipeline.py enhance phase.
"""

import argparse
import base64
import json
import os
import sys
import time
import urllib.request
import urllib.error

CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".claude", "gemini_image_config.json")


def load_config():
    if not os.path.isfile(CONFIG_PATH):
        print(f"ERROR: config not found: {CONFIG_PATH}", file=sys.stderr)
        sys.exit(1)
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def image_to_base64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def detect_mime(path):
    ext = os.path.splitext(path)[1].lower()
    return {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "webp": "image/webp"}.get(ext.lstrip("."), "image/png")


def call_gemini_api(config, prompt, image_path, reference_path=None,
                    model=None, seed=None, temperature=None):
    api_base = config["api_base_url"].rstrip("/")
    api_key = config["api_key"]
    model_id = model or config.get("model", "gemini-3-pro-image-preview")

    url = f"{api_base}/v1/chat/completions"

    # Build content array
    content = []
    # Text prompt first
    content.append({"type": "text", "text": prompt})
    # Source image
    b64_img = image_to_base64(image_path)
    mime = detect_mime(image_path)
    content.append({
        "type": "image_url",
        "image_url": {"url": f"data:{mime};base64,{b64_img}"}
    })
    # Reference image (optional)
    if reference_path and os.path.isfile(reference_path):
        b64_ref = image_to_base64(reference_path)
        mime_ref = detect_mime(reference_path)
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mime_ref};base64,{b64_ref}"}
        })

    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 4096,
    }
    if temperature is not None:
        payload["temperature"] = temperature
    if seed is not None:
        payload["seed"] = seed

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"API error {e.code}: {body}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Connection error: {e.reason}", file=sys.stderr)
        sys.exit(1)

    return result


def extract_image_from_response(result):
    """Extract base64 image data from OpenAI-compatible response."""
    choices = result.get("choices", [])
    if not choices:
        return None, None

    message = choices[0].get("message", {})
    content = message.get("content", "")

    # Case 1: content is a list (multimodal response)
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict):
                # image_url format
                if part.get("type") == "image_url":
                    url = part.get("image_url", {}).get("url", "")
                    if url.startswith("data:"):
                        # data:image/png;base64,xxxx
                        header, b64data = url.split(",", 1)
                        ext = "png"
                        if "jpeg" in header or "jpg" in header:
                            ext = "jpg"
                        elif "webp" in header:
                            ext = "webp"
                        return base64.b64decode(b64data), ext
                # inline_data format (Gemini native)
                if "inline_data" in part:
                    b64data = part["inline_data"].get("data", "")
                    mime = part["inline_data"].get("mime_type", "image/png")
                    ext = "jpg" if "jpeg" in mime else ("webp" if "webp" in mime else "png")
                    return base64.b64decode(b64data), ext
    # Case 2: content is a string (some proxies embed base64 in text)
    elif isinstance(content, str):
        # Check for base64 image pattern
        import re
        m = re.search(r'data:(image/\w+);base64,([A-Za-z0-9+/=]+)', content)
        if m:
            mime = m.group(1)
            ext = "jpg" if "jpeg" in mime else ("webp" if "webp" in mime else "png")
            return base64.b64decode(m.group(2)), ext

    # Case 3: check for b64_json in message
    if "b64_json" in str(result):
        # Try to find it
        for choice in choices:
            msg = choice.get("message", {})
            if "b64_json" in str(msg):
                import re
                m = re.search(r'"b64_json"\s*:\s*"([^"]+)"', json.dumps(msg))
                if m:
                    return base64.b64decode(m.group(1)), "png"

    return None, None


def main():
    parser = argparse.ArgumentParser(description="Gemini image generation")
    parser.add_argument("--prompt", help="Prompt text")
    parser.add_argument("--prompt-file", help="Path to prompt text file")
    parser.add_argument("--image", required=True, help="Source image path")
    parser.add_argument("--reference", help="Reference image path")
    parser.add_argument("--model", help="Model ID override")
    parser.add_argument("--seed", type=int, help="Seed for reproducibility")
    parser.add_argument("--temperature", type=float, help="Temperature")
    parser.add_argument("--config", help="Run config wizard (unused, for compat)")
    args = parser.parse_args()

    # Load prompt
    prompt = args.prompt or ""
    if args.prompt_file and os.path.isfile(args.prompt_file):
        with open(args.prompt_file, encoding="utf-8") as f:
            prompt = f.read()
    if not prompt:
        print("ERROR: no prompt provided", file=sys.stderr)
        sys.exit(1)

    config = load_config()

    print(f"Gemini enhance: {os.path.basename(args.image)}")
    print(f"  Model: {args.model or config.get('model', 'default')}")
    print(f"  Prompt: {len(prompt)} chars")

    result = call_gemini_api(
        config, prompt, args.image,
        reference_path=args.reference,
        model=args.model,
        seed=args.seed,
        temperature=args.temperature,
    )

    img_data, ext = extract_image_from_response(result)
    if not img_data:
        print("ERROR: no image in API response", file=sys.stderr)
        print(f"Response keys: {list(result.keys())}", file=sys.stderr)
        if "choices" in result:
            c = result["choices"][0] if result["choices"] else {}
            msg = c.get("message", {})
            content = msg.get("content", "")
            if isinstance(content, str):
                print(f"Content (text): {content[:500]}", file=sys.stderr)
            elif isinstance(content, list):
                for i, part in enumerate(content):
                    if isinstance(part, dict):
                        print(f"Content[{i}] type={part.get('type', '?')}", file=sys.stderr)
        sys.exit(1)

    # Save output — always convert to JPG for consistency
    from PIL import Image
    import io

    src_dir = os.path.dirname(args.image)
    src_stem = os.path.splitext(os.path.basename(args.image))[0]
    out_path = os.path.join(src_dir, f"{src_stem}_enhanced.jpg")

    img = Image.open(io.BytesIO(img_data)).convert("RGB")
    img.save(out_path, "JPEG", quality=95)


    print(f"SAVED_IMAGE: {out_path}")
    print(f"图片已保存: {out_path}")


if __name__ == "__main__":
    main()
