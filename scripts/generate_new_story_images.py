"""Generate cover images and character portraits for Edda's Trust and The Sunken Archive.

Usage:
    python scripts/generate_new_story_images.py [--comfyui http://192.168.50.90:8188]
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

WORKFLOW_TEMPLATE = {
    "3": {
        "class_type": "KSampler",
        "inputs": {
            "cfg": 1.0, "denoise": 1.0,
            "latent_image": ["5", 0], "model": ["4", 0],
            "negative": ["7", 0], "positive": ["6", 0],
            "sampler_name": "euler", "scheduler": "normal",
            "seed": 0, "steps": 20,
        },
    },
    "4": {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {"ckpt_name": "flux1-dev-fp8.safetensors"},
    },
    "5": {
        "class_type": "EmptyLatentImage",
        "inputs": {"batch_size": 1, "height": 1024, "width": 1024},
    },
    "6": {
        "class_type": "CLIPTextEncode",
        "inputs": {"clip": ["4", 1], "text": ""},
    },
    "7": {
        "class_type": "CLIPTextEncode",
        "inputs": {"clip": ["4", 1], "text": ""},
    },
    "8": {
        "class_type": "VAEDecode",
        "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
    },
    "9": {
        "class_type": "SaveImage",
        "inputs": {"filename_prefix": "RPGEngine", "images": ["8", 0]},
    },
}

IMAGES = [
    # ── COVERS ──────────────────────────────────────────────
    {
        "name": "covers/story_eddas_trust",
        "prompt": (
            "medieval fantasy market square at golden hour, warm sunlight on cobblestones, "
            "a single spice stall with colorful jars and hanging herbs, a sturdy woman "
            "restacking crates alone, cozy European village feel, oil painting style, "
            "rich warm palette, painterly brushstrokes, soft depth of field, "
            "intimate trust-building mood, wide banner composition"
        ),
        "width": 800,
        "height": 500,
    },
    {
        "name": "covers/story_sunken_archive",
        "prompt": (
            "underwater ruins of a sunken stone library, shafts of light piercing murky water, "
            "schools of silver fish swimming between collapsed bookshelves, barnacle-covered arches, "
            "a dive light beam cutting through the deep blue gloom, coral growing on carved stone, "
            "watercolor illustration style, teal and deep blue palette with golden light accents, "
            "mysterious atmospheric adventure mood, wide banner composition"
        ),
        "width": 800,
        "height": 500,
    },
    {
        "name": "covers/story_sessions",
        "prompt": (
            "quiet therapy office interior, two leather armchairs facing each other, "
            "soft lamp light, a box of tissues on a side table, rain on the window, "
            "muted warm tones, impressionist style, soft brushstrokes, "
            "intimate emotional drama mood, wide banner composition"
        ),
        "width": 800,
        "height": 500,
    },
    {
        "name": "covers/story_wolves_of_ashenmoor",
        "prompt": (
            "dark gothic village at twilight, twisted bare trees, distant wolf silhouettes "
            "on a misty ridge, flickering torch light from a stone tavern, "
            "dark fantasy woodcut illustration style, muted earth tones with amber highlights, "
            "eerie foreboding mood, wide banner composition"
        ),
        "width": 800,
        "height": 500,
    },

    # ── EDDA'S TRUST — Characters ───────────────────────────
    {
        "name": "portraits/edda",
        "prompt": (
            "portrait of a sturdy middle-aged woman merchant, weathered kind face, "
            "sharp watchful eyes, hair tied back with a cloth scarf, earth-toned apron "
            "over simple linen clothes, spice dust on her hands, warm market stall "
            "background with hanging herbs, oil painting style, painterly brushstrokes, "
            "warm golden light, head and shoulders, fantasy RPG character portrait"
        ),
        "width": 512,
        "height": 512,
    },

    # ── THE SUNKEN ARCHIVE — Characters ─────────────────────
    {
        "name": "portraits/maren",
        "prompt": (
            "portrait of a weathered old fisherwoman in her 70s, deep lines on her face, "
            "silver hair under a dark wool cap, stern jaw, piercing blue eyes that have seen "
            "too much, heavy oilskin coat with salt stains, coiled rope over one shoulder, "
            "stormy grey sea background, watercolor illustration style, "
            "teal and grey palette, head and shoulders, character portrait"
        ),
        "width": 512,
        "height": 512,
    },
    {
        "name": "portraits/fox",
        "prompt": (
            "portrait of an eager young marine archaeologist in their late 20s, "
            "short messy sun-bleached hair, bright excited eyes behind diving goggles "
            "pushed up on forehead, wetsuit half-unzipped showing a faded university tshirt, "
            "holding a waterproof notebook, boat deck and ocean background, "
            "watercolor illustration style, warm teal palette, "
            "head and shoulders, character portrait"
        ),
        "width": 512,
        "height": 512,
    },
]


def make_workflow(prompt, width, height, prefix):
    wf = json.loads(json.dumps(WORKFLOW_TEMPLATE))
    wf["6"]["inputs"]["text"] = prompt
    wf["5"]["inputs"]["width"] = width
    wf["5"]["inputs"]["height"] = height
    wf["3"]["inputs"]["seed"] = random.randint(0, 2**32)
    wf["9"]["inputs"]["filename_prefix"] = prefix
    return wf


def queue_prompt(workflow, server):
    payload = json.dumps({"prompt": workflow}).encode()
    req = urllib.request.Request(
        f"{server}/prompt", data=payload,
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req)
    return json.loads(resp.read())["prompt_id"]


def wait_for_completion(prompt_id, server, timeout=300):
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


def download_image(filename, subfolder, server, output_path):
    url = f"{server}/view?filename={filename}&subfolder={subfolder}&type=output"
    urllib.request.urlretrieve(url, output_path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--comfyui", default=COMFYUI_URL)
    parser.add_argument("--only", help="Generate only this image name")
    args = parser.parse_args()

    os.makedirs(os.path.join(OUTPUT_DIR, "covers"), exist_ok=True)
    os.makedirs(os.path.join(OUTPUT_DIR, "portraits"), exist_ok=True)

    images = IMAGES
    if args.only:
        images = [i for i in images if i["name"] == args.only]
        if not images:
            print(f"Unknown: {args.only}")
            print(f"Available: {', '.join(i['name'] for i in IMAGES)}")
            sys.exit(1)

    print(f"Generating {len(images)} images via {args.comfyui}\n")

    for img in images:
        name = img["name"]
        print(f"[{name}] Queuing ({img['width']}x{img['height']})...")
        workflow = make_workflow(img["prompt"], img["width"], img["height"], f"rpg_{name.replace('/', '_')}")

        try:
            prompt_id = queue_prompt(workflow, args.comfyui)
            print(f"[{name}] Waiting...")
            result = wait_for_completion(prompt_id, args.comfyui)

            for node_id, node_output in result.get("outputs", {}).items():
                if "images" in node_output:
                    for image_info in node_output["images"]:
                        filename = image_info["filename"]
                        subfolder = image_info.get("subfolder", "")
                        output_path = os.path.join(OUTPUT_DIR, f"{name}.png")
                        download_image(filename, subfolder, args.comfyui, output_path)
                        print(f"[{name}] ✓ Saved")
                        break
                    break
        except Exception as e:
            print(f"[{name}] ERROR: {e}")

    print("\nDone!")


if __name__ == "__main__":
    main()
