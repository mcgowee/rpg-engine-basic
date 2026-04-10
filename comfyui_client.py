"""ComfyUI API client — sends workflows and retrieves generated images.

Supports two checkpoints:
- flux1-dev-fp8.safetensors  — default, best for SFW content
- ponyDiffusionV6XL.safetensors — SDXL-based, best for NSFW content
"""

import json
import os
import random
import time
import logging
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

COMFYUI_URL = os.environ.get("COMFYUI_URL", "http://192.168.50.90:8188")

# --- Checkpoint configs ---

CHECKPOINTS = {
    "flux": {
        "ckpt_name": "flux1-dev-fp8.safetensors",
        "cfg": 1.0,
        "steps": 20,
        "sampler_name": "euler",
        "scheduler": "normal",
        "negative_prompt": "",
    },
    "pony": {
        "ckpt_name": "ponyDiffusionV6XL.safetensors",
        "cfg": 7.0,
        "steps": 25,
        "sampler_name": "euler_ancestral",
        "scheduler": "normal",
        "negative_prompt": (
            "score_1, score_2, score_3, deformed, ugly, blurry, bad anatomy, "
            "bad proportions, extra limbs, mutated hands, poorly drawn face, "
            "watermark, text, signature, logo"
        ),
    },
}

# Pony quality tags prepended to positive prompts
PONY_QUALITY_PREFIX = "score_9, score_8_up, score_7_up, "

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
            "steps": 20,
        },
    },
    "4": {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {"ckpt_name": "flux1-dev-fp8.safetensors"},
    },
    "5": {
        "class_type": "EmptyLatentImage",
        "inputs": {"batch_size": 1, "height": 500, "width": 800},
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
        "inputs": {"filename_prefix": "cover", "images": ["8", 0]},
    },
}


def is_available() -> bool:
    """Check if ComfyUI is reachable."""
    try:
        resp = urllib.request.urlopen(f"{COMFYUI_URL}/system_stats", timeout=3)
        return resp.status == 200
    except Exception:
        return False


def _pick_checkpoint(nsfw_rating: str = "none") -> str:
    """Return checkpoint key based on NSFW rating."""
    if nsfw_rating in ("mature", "explicit", "extreme"):
        return "pony"
    return "flux"


def generate_image(
    prompt: str,
    width: int = 800,
    height: int = 500,
    prefix: str = "cover",
    nsfw_rating: str = "none",
    negative_prompt: str | None = None,
) -> str | None:
    """Generate an image via ComfyUI. Returns the output filename or None on failure.

    Args:
        prompt: The positive prompt text.
        width: Image width in pixels.
        height: Image height in pixels.
        prefix: Filename prefix for the output.
        nsfw_rating: Story NSFW rating — "mature"/"explicit"/"extreme" use Pony, others use Flux.
        negative_prompt: Override the default negative prompt. If None, uses checkpoint default.
    """
    ckpt_key = _pick_checkpoint(nsfw_rating)
    ckpt = CHECKPOINTS[ckpt_key]

    # Build workflow from template
    wf = json.loads(json.dumps(WORKFLOW_TEMPLATE))

    # Apply checkpoint settings
    wf["4"]["inputs"]["ckpt_name"] = ckpt["ckpt_name"]
    wf["3"]["inputs"]["cfg"] = ckpt["cfg"]
    wf["3"]["inputs"]["steps"] = ckpt["steps"]
    wf["3"]["inputs"]["sampler_name"] = ckpt["sampler_name"]
    wf["3"]["inputs"]["scheduler"] = ckpt["scheduler"]

    # Pony needs SDXL-native resolution (1024x base) and quality score tags
    if ckpt_key == "pony":
        prompt = PONY_QUALITY_PREFIX + prompt
        # Scale up to SDXL-native if dimensions are below 1024 on longest side
        max_dim = max(width, height)
        if max_dim < 1024:
            scale = 1024 / max_dim
            width = int(width * scale)
            height = int(height * scale)
        # Round to nearest 8 (required by latent space)
        width = (width // 8) * 8
        height = (height // 8) * 8

    # Set prompt and dimensions
    wf["6"]["inputs"]["text"] = prompt
    wf["7"]["inputs"]["text"] = negative_prompt if negative_prompt is not None else ckpt["negative_prompt"]
    wf["5"]["inputs"]["width"] = width
    wf["5"]["inputs"]["height"] = height
    wf["3"]["inputs"]["seed"] = random.randint(0, 2**32)
    wf["9"]["inputs"]["filename_prefix"] = prefix

    logger.info("ComfyUI generate: checkpoint=%s, %dx%d, cfg=%s, steps=%s",
                ckpt["ckpt_name"], width, height, ckpt["cfg"], ckpt["steps"])

    try:
        # Queue the prompt
        payload = json.dumps({"prompt": wf}).encode()
        req = urllib.request.Request(
            f"{COMFYUI_URL}/prompt",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        prompt_id = data["prompt_id"]
        logger.info("ComfyUI prompt queued: %s", prompt_id)

        # Wait for completion
        start = time.time()
        timeout = 300
        while time.time() - start < timeout:
            try:
                resp = urllib.request.urlopen(f"{COMFYUI_URL}/history/{prompt_id}", timeout=5)
                history = json.loads(resp.read())
                if prompt_id in history:
                    # Find output image
                    outputs = history[prompt_id].get("outputs", {})
                    for node_output in outputs.values():
                        if "images" in node_output:
                            for img in node_output["images"]:
                                return img["filename"]
                    return None
            except Exception:
                pass
            time.sleep(2)

        logger.error("ComfyUI timed out after %ds", timeout)
        return None

    except Exception as e:
        logger.error("ComfyUI generation failed: %s", e)
        return None


def download_image(filename: str, save_path: str) -> bool:
    """Download a generated image from ComfyUI output to a local path."""
    try:
        url = f"{COMFYUI_URL}/view?filename={filename}&type=output"
        urllib.request.urlretrieve(url, save_path)
        return True
    except Exception as e:
        logger.error("Failed to download image %s: %s", filename, e)
        return False
