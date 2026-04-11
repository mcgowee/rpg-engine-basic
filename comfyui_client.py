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


def get_image_model_setting() -> str:
    """Read the global image model setting. Returns checkpoint key."""
    try:
        settings_path = os.path.join(os.path.dirname(__file__), "model_settings.json")
        if os.path.exists(settings_path):
            with open(settings_path) as f:
                import json
                settings = json.load(f)
                return settings.get("image_model", "flux")
    except Exception:
        pass
    return "flux"


def _pick_checkpoint(nsfw_rating: str = "none") -> str:
    """Return checkpoint key. Uses global setting, with NSFW override to Pony."""
    global_setting = get_image_model_setting()
    # NSFW stories always use Pony regardless of global setting
    if nsfw_rating in ("mature", "explicit", "extreme"):
        return "pony"
    # Otherwise use the global setting
    if global_setting in CHECKPOINTS:
        return global_setting
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


def generate_with_lora(
    prompt: str,
    lora_name: str,
    width: int = 1024,
    height: int = 576,
    prefix: str = "scene",
    lora_strength: float = 0.85,
    negative_prompt: str | None = None,
) -> str | None:
    """Generate an image with a character LoRA loaded on Juggernaut XL.

    Uses the standard SDXL checkpoint (Juggernaut XL) with a LoRA for character
    identity. The prompt should include the trigger word for the LoRA.

    Args:
        prompt: Text prompt (must include the LoRA trigger word).
        lora_name: LoRA filename (e.g. "alex_lora.safetensors").
        width: Output width.
        height: Output height.
        prefix: Filename prefix for the output.
        lora_strength: LoRA influence (0.0-1.0).
        negative_prompt: Override negative prompt.
    """
    neg = negative_prompt if negative_prompt is not None else (
        "deformed, ugly, blurry, bad anatomy, bad proportions, extra limbs, "
        "mutated hands, poorly drawn face, watermark, text, signature, logo"
    )

    # Juggernaut XL + LoraLoader workflow
    wf = {
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": IPADAPTER_CHECKPOINT},
        },
        "15": {
            "class_type": "LoraLoader",
            "inputs": {
                "model": ["4", 0],
                "clip": ["4", 1],
                "lora_name": lora_name,
                "strength_model": lora_strength,
                "strength_clip": lora_strength,
            },
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["15", 1], "text": prompt},
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["15", 1], "text": neg},
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"batch_size": 1, "height": height, "width": width},
        },
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["15", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0],
                "cfg": 6.5,
                "steps": 30,
                "sampler_name": "dpmpp_2m",
                "scheduler": "karras",
                "seed": random.randint(0, 2**32),
                "denoise": 1.0,
            },
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": prefix, "images": ["8", 0]},
        },
    }

    # Scale to SDXL native if needed
    max_dim = max(width, height)
    if max_dim < 1024:
        scale = 1024 / max_dim
        width = int(width * scale)
        height = int(height * scale)
    width = (width // 8) * 8
    height = (height // 8) * 8
    wf["5"]["inputs"]["width"] = width
    wf["5"]["inputs"]["height"] = height

    logger.info("ComfyUI LoRA generate: lora=%s, strength=%.2f, %dx%d", lora_name, lora_strength, width, height)

    try:
        payload = json.dumps({"prompt": wf}).encode()
        req = urllib.request.Request(
            f"{COMFYUI_URL}/prompt",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        prompt_id = data["prompt_id"]
        logger.info("ComfyUI LoRA prompt queued: %s", prompt_id)

        start = time.time()
        timeout = 300
        while time.time() - start < timeout:
            try:
                resp = urllib.request.urlopen(f"{COMFYUI_URL}/history/{prompt_id}", timeout=5)
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

        logger.error("ComfyUI LoRA timed out after %ds", timeout)
        return None

    except Exception as e:
        logger.error("ComfyUI LoRA generation failed: %s", e)
        return None


def upload_image(image_path: str) -> str | None:
    """Upload a local image to ComfyUI's input directory. Returns the filename on success."""
    import mimetypes

    filename = os.path.basename(image_path)
    content_type = mimetypes.guess_type(image_path)[0] or "image/png"

    try:
        with open(image_path, "rb") as f:
            image_data = f.read()

        # Build multipart/form-data body
        boundary = f"----ComfyUpload{random.randint(0, 2**32)}"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="image"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode() + image_data + f"\r\n--{boundary}--\r\n".encode()

        req = urllib.request.Request(
            f"{COMFYUI_URL}/upload/image",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=30)
        result = json.loads(resp.read())
        uploaded_name = result.get("name", filename)
        logger.info("Uploaded image to ComfyUI: %s → %s", image_path, uploaded_name)
        return uploaded_name
    except Exception as e:
        logger.error("Failed to upload image to ComfyUI: %s", e)
        return None


# --- IP-Adapter FaceID workflow (ComfyUI_IPAdapter_plus / cubiq) ---
# Uses IPAdapterUnifiedLoaderFaceID + IPAdapterFaceID with InsightFace for strong
# face identity locking. Much better consistency than Plus Face (CLIP-vision only).
# Always uses Juggernaut XL v8 (standard SDXL). Pony's latent space diverges too
# far from base SDXL and produces garbage with IP-Adapter conditioning.
#
# Required models on ComfyUI host:
#   models/checkpoints/juggernautXL_v8Rundiffusion.safetensors
#   models/ipadapter/ip-adapter-faceid-plusv2_sdxl.bin
#   models/loras/ip-adapter-faceid-plusv2_sdxl_lora.safetensors
#   models/insightface/models/buffalo_l/*.onnx  (5 files)
#   pip: insightface, onnxruntime-gpu

IPADAPTER_CHECKPOINT = "juggernautXL_v8Rundiffusion.safetensors"

IPADAPTER_WORKFLOW = {
    "4": {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {"ckpt_name": IPADAPTER_CHECKPOINT},
    },
    "20": {
        "class_type": "IPAdapterUnifiedLoaderFaceID",
        "inputs": {
            "model": ["4", 0],
            "preset": "FACEID PLUS V2",
            "lora_strength": 0.6,
            "provider": "CUDA",
        },
    },
    "12": {
        "class_type": "LoadImage",
        "inputs": {"image": "reference.png"},
    },
    "18": {
        "class_type": "IPAdapterFaceID",
        "inputs": {
            "model": ["20", 0],
            "ipadapter": ["20", 1],
            "image": ["12", 0],
            "weight": 0.85,
            "weight_faceidv2": 0.85,
            "weight_type": "linear",
            "combine_embeds": "concat",
            "start_at": 0.0,
            "end_at": 1.0,
            "embeds_scaling": "V only",
        },
    },
    "6": {
        "class_type": "CLIPTextEncode",
        "inputs": {"clip": ["4", 1], "text": ""},
    },
    "7": {
        "class_type": "CLIPTextEncode",
        "inputs": {"clip": ["4", 1], "text": ""},
    },
    "5": {
        "class_type": "EmptyLatentImage",
        "inputs": {"batch_size": 1, "height": 1024, "width": 768},
    },
    "3": {
        "class_type": "KSampler",
        "inputs": {
            "model": ["18", 0],
            "positive": ["6", 0],
            "negative": ["7", 0],
            "latent_image": ["5", 0],
            "cfg": 6.5,
            "steps": 30,
            "sampler_name": "dpmpp_2m",
            "scheduler": "karras",
            "seed": 0,
            "denoise": 1.0,
        },
    },
    "8": {
        "class_type": "VAEDecode",
        "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
    },
    "9": {
        "class_type": "SaveImage",
        "inputs": {"filename_prefix": "faceid", "images": ["8", 0]},
    },
}


def generate_with_face_ref(
    prompt: str,
    ref_image_path: str,
    width: int = 768,
    height: int = 768,
    prefix: str = "ipadapter",
    nsfw_rating: str = "none",
    negative_prompt: str | None = None,
    weight: float = 0.8,
) -> str | None:
    """Generate an image using IP-Adapter Plus Face with a reference image.

    Uses Juggernaut XL (standard SDXL) — required for IP-Adapter compatibility.
    Pony Diffusion's latent space diverges too far from base SDXL and produces
    garbage with IP-Adapter conditioning.

    Args:
        prompt: Text prompt describing the desired output.
        ref_image_path: Local path to the reference face image.
        width: Output width.
        height: Output height.
        prefix: Filename prefix for the output.
        nsfw_rating: Ignored — always uses Juggernaut XL regardless of NSFW rating.
        negative_prompt: Override negative prompt.
        weight: IP-Adapter influence strength (0.0-1.0). Higher = more like reference.
    """
    del nsfw_rating  # always Juggernaut XL for IP-Adapter Plus Face

    ref_name = upload_image(ref_image_path)
    if not ref_name:
        return None

    neg = negative_prompt if negative_prompt is not None else (
        "deformed, ugly, blurry, bad anatomy, bad proportions, extra limbs, "
        "mutated hands, poorly drawn face, watermark, text, signature, logo"
    )

    wf = json.loads(json.dumps(IPADAPTER_WORKFLOW))

    # Reference image
    wf["12"]["inputs"]["image"] = ref_name

    # FaceID weights
    wf["18"]["inputs"]["weight"] = float(weight)
    wf["18"]["inputs"]["weight_faceidv2"] = float(weight)

    # Prompts
    wf["6"]["inputs"]["text"] = prompt
    wf["7"]["inputs"]["text"] = neg

    # Dimensions (SDXL native)
    max_dim = max(width, height)
    if max_dim < 1024:
        scale = 1024 / max_dim
        width = int(width * scale)
        height = int(height * scale)
    width = (width // 8) * 8
    height = (height // 8) * 8
    wf["5"]["inputs"]["width"] = width
    wf["5"]["inputs"]["height"] = height

    # Sampler
    wf["3"]["inputs"]["seed"] = random.randint(0, 2**32)

    wf["9"]["inputs"]["filename_prefix"] = prefix

    logger.info(
        "ComfyUI FaceID generate: ref=%s, weight=%.2f, %dx%d",
        ref_name, weight, width, height,
    )

    try:
        payload = json.dumps({"prompt": wf}).encode()
        req = urllib.request.Request(
            f"{COMFYUI_URL}/prompt",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            resp = urllib.request.urlopen(req, timeout=10)
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            logger.error("ComfyUI /prompt rejected (%s): %s", e.code, err_body[:4000])
            return None
        data = json.loads(resp.read())
        prompt_id = data["prompt_id"]
        logger.info("ComfyUI IP-Adapter prompt queued: %s", prompt_id)

        start = time.time()
        timeout = 300
        while time.time() - start < timeout:
            try:
                resp = urllib.request.urlopen(f"{COMFYUI_URL}/history/{prompt_id}", timeout=5)
                history = json.loads(resp.read())
                if prompt_id in history:
                    entry = history[prompt_id]
                    status = entry.get("status", {})
                    if status.get("status_str") == "error":
                        logger.error(
                            "ComfyUI IP-Adapter graph error for %s: %s",
                            prompt_id,
                            status.get("messages", status),
                        )
                        return None
                    outputs = entry.get("outputs", {})
                    for node_output in outputs.values():
                        if "images" in node_output:
                            for img in node_output["images"]:
                                return img["filename"]
            except Exception:
                pass
            time.sleep(2)

        logger.error("ComfyUI IP-Adapter timed out after %ds", timeout)
        return None

    except Exception as e:
        logger.error("ComfyUI IP-Adapter generation failed: %s", e)
        return None
