"""Generate character portraits for all seed stories via ComfyUI.

Usage:
    python scripts/generate_portraits.py [--comfyui http://192.168.50.90:8188]

First uses the local LLM (Ollama) to convert personality prompts to
visual descriptions, then sends them to ComfyUI for image generation.
Saves portraits to web/static/images/portraits/ and updates the
story JSON files with the portrait filenames.
"""

import argparse
import json
import os
import sys

# Add parent dir to path so we can import project modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

COMFYUI_URL = "http://192.168.50.90:8188"
STORIES_DIR = os.path.join(os.path.dirname(__file__), "..", "stories")
PORTRAITS_DIR = os.path.join(os.path.dirname(__file__), "..", "web", "static", "images", "portraits")


def get_visual_description(character_name: str, personality: str, genre: str) -> str:
    """Use the LLM to convert a personality prompt to a visual description."""
    try:
        from llm import get_llm
        llm = get_llm()
        prompt = f"""Based on this RPG character description, write a short physical appearance description (2-3 sentences) for generating a portrait image. Focus on: face, hair, clothing, expression, age, build. Do not include personality or behavior — only visual details.

Character name: {character_name}
Genre: {genre}
Personality description: {personality}

Physical appearance:"""
        result = llm.invoke(prompt)
        if isinstance(result, str):
            return result.strip()
        return str(getattr(result, 'content', result)).strip()
    except Exception as e:
        print(f"  LLM failed: {e}")
        return f"{character_name}, {genre} character"


def generate_portrait(prompt: str, width: int, height: int, prefix: str, comfyui_url: str) -> str | None:
    """Generate a portrait via ComfyUI. Returns filename or None."""
    import urllib.request
    import time
    import random

    WORKFLOW = {
        "3": {"class_type": "KSampler", "inputs": {
            "cfg": 1.0, "denoise": 1.0, "latent_image": ["5", 0],
            "model": ["4", 0], "negative": ["7", 0], "positive": ["6", 0],
            "sampler_name": "euler", "scheduler": "normal",
            "seed": random.randint(0, 2**32), "steps": 20,
        }},
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "flux1-dev-fp8.safetensors"}},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"batch_size": 1, "height": height, "width": width}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["4", 1], "text": prompt}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["4", 1], "text": ""}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
        "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": prefix, "images": ["8", 0]}},
    }

    payload = json.dumps({"prompt": WORKFLOW}).encode()
    req = urllib.request.Request(f"{comfyui_url}/prompt", data=payload, headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req, timeout=10)
    data = json.loads(resp.read())
    prompt_id = data["prompt_id"]

    start = time.time()
    while time.time() - start < 300:
        try:
            resp = urllib.request.urlopen(f"{comfyui_url}/history/{prompt_id}", timeout=5)
            history = json.loads(resp.read())
            if prompt_id in history:
                outputs = history[prompt_id].get("outputs", {})
                for node_output in outputs.values():
                    if "images" in node_output:
                        for img in node_output["images"]:
                            return img["filename"]
                return None
        except Exception:
            pass
        time.sleep(2)
    return None


def download_image(comfyui_url: str, filename: str, save_path: str):
    import urllib.request
    url = f"{comfyui_url}/view?filename={filename}&type=output"
    urllib.request.urlretrieve(url, save_path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--comfyui", default=COMFYUI_URL)
    parser.add_argument("--skip-llm", action="store_true", help="Skip LLM visual description, use raw personality")
    args = parser.parse_args()

    os.makedirs(PORTRAITS_DIR, exist_ok=True)

    stories = sorted(f for f in os.listdir(STORIES_DIR) if f.endswith(".json"))
    total = 0

    for story_file in stories:
        path = os.path.join(STORIES_DIR, story_file)
        with open(path) as f:
            story = json.load(f)

        characters = story.get("characters", {})
        if not characters:
            continue

        title = story.get("title", story_file)
        genre = story.get("genre", "fantasy")
        print(f"\n=== {title} ===")

        updated = False
        for char_key, char_data in characters.items():
            if not isinstance(char_data, dict):
                continue

            label = char_key.replace("_", " ").title()
            personality = char_data.get("prompt", "")

            # Check if portrait already exists
            existing = char_data.get("portrait", "")
            if existing and os.path.exists(os.path.join(PORTRAITS_DIR, existing)):
                print(f"  [{char_key}] Portrait exists: {existing}, skipping")
                continue

            print(f"  [{char_key}] Getting visual description...")
            if args.skip_llm:
                visual_desc = f"{label}, {genre} character"
            else:
                visual_desc = get_visual_description(label, personality, genre)
            print(f"  [{char_key}] Visual: {visual_desc[:80]}...")

            comfyui_prompt = f"{visual_desc}, portrait, head and shoulders, dark atmospheric background, RPG character art, detailed face, cinematic lighting"

            print(f"  [{char_key}] Generating portrait (512x768)...")
            prefix = f"portrait_seed_{char_key}"
            comfyui_filename = generate_portrait(comfyui_prompt, 512, 768, prefix, args.comfyui)
            if not comfyui_filename:
                print(f"  [{char_key}] FAILED")
                continue

            local_filename = f"seed_{char_key}.png"
            local_path = os.path.join(PORTRAITS_DIR, local_filename)
            download_image(args.comfyui, comfyui_filename, local_path)
            print(f"  [{char_key}] Saved: {local_path}")

            char_data["portrait"] = local_filename
            updated = True
            total += 1

        if updated:
            with open(path, "w") as f:
                json.dump(story, f, indent=2, ensure_ascii=False)
                f.write("\n")
            print(f"  Updated {story_file}")

    print(f"\nDone! Generated {total} portraits.")


if __name__ == "__main__":
    main()
