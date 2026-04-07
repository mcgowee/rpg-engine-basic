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
        "prompt": "wide panoramic dark fantasy landscape, ancient ruins and mountains, dramatic sky with aurora and stars, RPG adventure concept art, cinematic, atmospheric, moody, epic scale",
        "width": 1536,
        "height": 512,
    },
    {
        "name": "login-bg",
        "prompt": "dark mysterious library interior, ancient books and scrolls, candlelight, dust motes in light beams, fantasy RPG atmosphere, moody, cinematic lighting",
        "width": 1024,
        "height": 1024,
    },
    {
        "name": "genre-mystery",
        "prompt": "dark foggy alley at night, cobblestone street, single gas lamp, detective noir atmosphere, mystery, shadows, cinematic",
        "width": 800,
        "height": 500,
    },
    {
        "name": "genre-thriller",
        "prompt": "tense scene, figure in shadows watching from a window, rain on glass, urban night, danger, thriller atmosphere, cinematic",
        "width": 800,
        "height": 500,
    },
    {
        "name": "genre-drama",
        "prompt": "two silhouettes facing each other across a candlelit table, emotional tension, warm and cold lighting contrast, dramatic, cinematic",
        "width": 800,
        "height": 500,
    },
    {
        "name": "genre-comedy",
        "prompt": "warm cozy fantasy tavern interior, fireplace, tankards of ale, friendly atmosphere, warm golden lighting, whimsical, inviting",
        "width": 800,
        "height": 500,
    },
    {
        "name": "genre-sci-fi",
        "prompt": "futuristic space station corridor, holographic displays, neon blue and purple lights, sci-fi atmosphere, sleek, cinematic",
        "width": 800,
        "height": 500,
    },
    {
        "name": "genre-horror",
        "prompt": "abandoned dark mansion hallway, cracked walls, single flickering light, something lurking in shadows, horror atmosphere, dread, cinematic",
        "width": 800,
        "height": 500,
    },
    {
        "name": "genre-fantasy",
        "prompt": "epic fantasy castle on a mountain peak, dragons in the sky, magical aurora, vast landscape below, fantasy RPG concept art, epic, cinematic",
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
