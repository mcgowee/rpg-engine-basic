"""Generate site images via ComfyUI API.

Usage:
    python scripts/generate_site_images.py [--comfyui http://192.168.50.90:8188]

Generates hero banner, login background, and genre thumbnails.
Saves to web/static/images/.
"""

import argparse
import json
import os
import random
import sys
import time
import urllib.request
import urllib.error

COMFYUI_URL = "http://192.168.50.90:8188"
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "web", "static", "images")

# Workflow template matching the FluxForRPG workflow
WORKFLOW_TEMPLATE = {
    "3": {
        "class_type": "KSampler",
        "inputs": {
            "cfg": 1.0,
            "denoise": 1.0,
            "latent_image": ["5", 0],
            "model": ["4", 0],
            "negative": ["7", 0],
            "positive": ["6", 0],
            "sampler_name": "euler",
            "scheduler": "normal",
            "seed": 0,
            "steps": 20
        }
    },
    "4": {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {
            "ckpt_name": "flux1-dev-fp8.safetensors"
        }
    },
    "5": {
        "class_type": "EmptyLatentImage",
        "inputs": {
            "batch_size": 1,
            "height": 1024,
            "width": 1024
        }
    },
    "6": {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "clip": ["4", 1],
            "text": ""
        }
    },
    "7": {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "clip": ["4", 1],
            "text": ""
        }
    },
    "8": {
        "class_type": "VAEDecode",
        "inputs": {
            "samples": ["3", 0],
            "vae": ["4", 2]
        }
    },
    "9": {
        "class_type": "SaveImage",
        "inputs": {
            "filename_prefix": "RPGEngine",
            "images": ["8", 0]
        }
    }
}

IMAGES_TO_GENERATE = [
    {
        "name": "hero",
        "prompt": "wide panoramic fantasy adventure landscape, rolling green hills, sparkling river, distant castle and floating islands, bright golden daylight, anime RPG key art, cel-shaded style, playful whimsical details, saturated cheerful colors, upbeat heroic mood, epic scale",
        "width": 1536,
        "height": 512,
    },
    {
        "name": "login-bg",
        "prompt": "cozy magical academy library interior, colorful books and floating runes, sunlight through tall windows, soft sparkles, anime RPG background art, cel-shaded style, bright warm palette, friendly adventurous vibe, whimsical and fun",
        "width": 1024,
        "height": 1024,
    },
    {
        "name": "genre-mystery",
        "prompt": "charming mystery town street in early evening, glowing lanterns, colorful shop signs, gentle mist and clues hidden in scene, anime detective RPG art, cel-shaded style, vivid playful palette, curious fun adventure mood",
        "width": 800,
        "height": 500,
    },
    {
        "name": "genre-thriller",
        "prompt": "sleek high-speed train racing through night countryside, motion blur on rails and windows, warm interior cabin lights vs cold blue moonlight outside, long dramatic perspective down the aisle or along the exterior, suspenseful thriller mood, anime RPG illustration, cel-shaded style, cinematic wide banner composition",
        "width": 800,
        "height": 500,
    },
    {
        "name": "genre-drama",
        "prompt": "emotional reunion on a rain-cleared street with rainbow reflections, expressive anime RPG characters, cel-shaded style, colorful cinematic lighting, heartfelt dramatic mood",
        "width": 800,
        "height": 500,
    },
    {
        "name": "genre-comedy",
        "prompt": "playful fantasy tavern party, chibi mascot creatures, confetti and warm lights, anime RPG illustration, cel-shaded style, bright colorful fun atmosphere",
        "width": 800,
        "height": 500,
    },
    {
        "name": "genre-sci-fi",
        "prompt": "bright futuristic city skyway with holographic signs, anime sci-fi RPG background, cel-shaded style, cyan-magenta highlights, clean energetic adventurous vibe",
        "width": 800,
        "height": 500,
    },
    {
        "name": "genre-horror",
        "prompt": "haunted carnival at twilight with glowing pumpkins and friendly ghostly silhouettes, anime horror RPG art, cel-shaded style, spooky but colorful playful mood",
        "width": 800,
        "height": 500,
    },
    {
        "name": "genre-romance",
        "prompt": "sunset garden promenade with flower petals and lanterns, anime romance RPG art, cel-shaded style, warm pink-gold palette, dreamy joyful mood",
        "width": 800,
        "height": 500,
    },
    {
        "name": "genre-slice-of-life",
        "prompt": "cozy town market street in daytime, friendly stalls and smiling townsfolk, anime slice-of-life RPG background, cel-shaded style, soft bright colors, wholesome vibe",
        "width": 800,
        "height": 500,
    },
    {
        "name": "genre-historical",
        "prompt": "vibrant historical city square with banners and stone architecture, anime historical RPG art, cel-shaded style, bright daylight, lively cultural atmosphere",
        "width": 800,
        "height": 500,
    },
    {
        "name": "genre-supernatural",
        "prompt": "sacred shrine under glowing spirit lights, floating talismans and foxfire, anime supernatural RPG background, cel-shaded style, bright mystical palette, wonder-filled mood",
        "width": 800,
        "height": 500,
    },
    {
        "name": "genre-post-apocalyptic",
        "prompt": "green reclaimed ruins with community camp and wind turbines, anime post-apocalyptic RPG art, cel-shaded style, hopeful bright skies, resilient adventurous mood",
        "width": 800,
        "height": 500,
    },
    {
        "name": "genre-urban-fantasy",
        "prompt": "modern city street with glowing magic sigils and floating spell signs, anime urban fantasy RPG background, cel-shaded style, colorful neon daylight blend, exciting playful mood",
        "width": 800,
        "height": 500,
    },
    {
        "name": "genre-erotica",
        "prompt": "elegant velvet lounge with candles and rose accents, anime romance RPG illustration, cel-shaded style, warm rich colors, tasteful intimate atmosphere",
        "width": 800,
        "height": 500,
    },
    {
        "name": "genre-fantasy",
        "prompt": "bright fantasy kingdom with shining castle, friendly dragon companions in blue sky, rainbow magic trails, anime RPG concept art, cel-shaded style, colorful whimsical world, joyful adventurous mood, fun and heroic",
        "width": 800,
        "height": 500,
    },
    {
        "name": "empty-stories",
        "prompt": "young adventurer at a colorful quest board in a cheerful fantasy town square, anime RPG illustration, cel-shaded style, bright daylight, inviting and motivational mood",
        "width": 1024,
        "height": 640,
    },
    {
        "name": "empty-browse",
        "prompt": "traveler looking at a magical map with glowing pins in a lively guild hall, anime RPG illustration, cel-shaded style, bright playful colors, discovery mood",
        "width": 1024,
        "height": 640,
    },
    {
        "name": "empty-books",
        "prompt": "cozy fantasy study desk with a blank glowing storybook and floating sparkles, anime RPG illustration, cel-shaded style, warm bright palette, creative welcoming mood",
        "width": 1024,
        "height": 640,
    },
    {
        "name": "docs-playing-hero",
        "prompt": "anime RPG party exploring bright ancient ruins with clear paths and landmarks, cel-shaded style, vibrant sky, adventurous instructional banner composition",
        "width": 1280,
        "height": 480,
    },
    {
        "name": "docs-stories-hero",
        "prompt": "anime RPG creator desk with magical pen drawing maps and character cards, bright colorful workshop, cel-shaded style, inspirational banner composition",
        "width": 1280,
        "height": 480,
    },
    {
        "name": "docs-engine-hero",
        "prompt": "fantasy-tech command room with glowing node graph holograms and branching pathways, anime RPG systems art, cel-shaded style, bright readable banner composition",
        "width": 1280,
        "height": 480,
    },
    {
        "name": "graph-empty",
        "prompt": "clean fantasy blueprint table showing connected node symbols and arrows, anime RPG UI art, cel-shaded style, bright neutral palette",
        "width": 1024,
        "height": 640,
    },
    {
        "name": "settings-models",
        "prompt": "anime mage selecting glowing model orbs from organized shelves, bright magical lab, cel-shaded style, friendly technical mood",
        "width": 1024,
        "height": 640,
    },
    # Story card covers (web/static/images/covers/ — referenced by stories.cover_image)
    {
        "name": "covers/story_midnight_lighthouse",
        "prompt": "dramatic coastal lighthouse on a stormy cliff at night, rotating beam cutting through rain and mist, waves crashing on rocks, warm lantern glow from tower windows, anime RPG illustration, cel-shaded style, cinematic wide banner composition, mystery adventure mood",
        "width": 800,
        "height": 500,
    },
    {
        "name": "covers/story_interrogation",
        "prompt": "small police interrogation room, metal table, harsh single overhead lamp, two-way mirror hint, empty chair, tense noir anime RPG scene, cel-shaded style, moody shadows, thriller mood, wide banner composition",
        "width": 800,
        "height": 500,
    },
    {
        "name": "covers/story_job_interview",
        "prompt": "bright modern corporate conference room, glass walls, long table — two interviewers across from viewer: a sharp professional East Asian woman with a red pen and papers, and a friendly heavyset man in relaxed shirt leaning back smiling, empty chair in foreground for candidate, anime RPG illustration, cel-shaded style, warm professional daylight, drama comedy job interview mood, wide banner",
        "width": 800,
        "height": 500,
    },
    {
        "name": "covers/story_spy_rolling_memory",
        "prompt": "stylish spy thriller, foreign embassy gala at night, chandeliers and flags, agent in formal suit blending into crowd, hint of danger and champagne, city skyline through windows, anime espionage RPG art, cel-shaded style, rich saturated colors, suspenseful cinematic wide banner",
        "width": 800,
        "height": 500,
    },
]


def make_workflow(prompt: str, width: int, height: int, prefix: str) -> dict:
    """Build a ComfyUI workflow from the template."""
    wf = json.loads(json.dumps(WORKFLOW_TEMPLATE))
    wf["6"]["inputs"]["text"] = prompt
    wf["5"]["inputs"]["width"] = width
    wf["5"]["inputs"]["height"] = height
    wf["3"]["inputs"]["seed"] = random.randint(0, 2**32)
    wf["9"]["inputs"]["filename_prefix"] = prefix
    return wf


def queue_prompt(workflow: dict, server: str) -> str:
    """Send a workflow to ComfyUI and return the prompt_id."""
    payload = json.dumps({"prompt": workflow}).encode()
    req = urllib.request.Request(
        f"{server}/prompt",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req)
    data = json.loads(resp.read())
    return data["prompt_id"]


def wait_for_completion(prompt_id: str, server: str, timeout: int = 300) -> dict:
    """Poll until the prompt is done. Returns the output info."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = urllib.request.urlopen(f"{server}/history/{prompt_id}")
            history = json.loads(resp.read())
            if prompt_id in history:
                return history[prompt_id]
        except Exception:
            pass
        time.sleep(2)
    raise TimeoutError(f"Prompt {prompt_id} didn't complete in {timeout}s")


def download_image(filename: str, subfolder: str, server: str, output_path: str):
    """Download a generated image from ComfyUI."""
    url = f"{server}/view?filename={filename}&subfolder={subfolder}&type=output"
    urllib.request.urlretrieve(url, output_path)


def main():
    parser = argparse.ArgumentParser(description="Generate site images via ComfyUI")
    parser.add_argument("--comfyui", default=COMFYUI_URL, help="ComfyUI server URL")
    parser.add_argument("--only", help="Generate only this image name (e.g. 'hero')")
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    images = IMAGES_TO_GENERATE
    if args.only:
        images = [i for i in images if i["name"] == args.only]
        if not images:
            print(f"Unknown image: {args.only}")
            print(f"Available: {', '.join(i['name'] for i in IMAGES_TO_GENERATE)}")
            sys.exit(1)

    print(f"Generating {len(images)} images via {args.comfyui}")
    print(f"Output: {os.path.abspath(OUTPUT_DIR)}")
    print()

    for img in images:
        name = img["name"]
        print(f"[{name}] Queuing ({img['width']}x{img['height']})...")

        workflow = make_workflow(img["prompt"], img["width"], img["height"], f"rpg_{name}")

        try:
            prompt_id = queue_prompt(workflow, args.comfyui)
            print(f"[{name}] Prompt ID: {prompt_id}, waiting...")

            result = wait_for_completion(prompt_id, args.comfyui)

            # Find the output image
            outputs = result.get("outputs", {})
            for node_id, node_output in outputs.items():
                if "images" in node_output:
                    for image_info in node_output["images"]:
                        filename = image_info["filename"]
                        subfolder = image_info.get("subfolder", "")
                        ext = os.path.splitext(filename)[1] or ".png"
                        output_path = os.path.join(OUTPUT_DIR, f"{name}{ext}")
                        download_image(filename, subfolder, args.comfyui, output_path)
                        print(f"[{name}] Saved: {output_path}")
                        break
                    break

        except Exception as e:
            print(f"[{name}] ERROR: {e}")
            continue

    print()
    print("Done! Images saved to web/static/images/")


if __name__ == "__main__":
    main()
