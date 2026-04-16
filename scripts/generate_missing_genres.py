"""Generate missing genre fallback images."""
import json, os, random, sys, time, urllib.request

COMFYUI_URL = "http://192.168.50.90:8188"
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "web", "static", "images")

WORKFLOW_TEMPLATE = {
    "3": {"class_type": "KSampler", "inputs": {"cfg": 1.0, "denoise": 1.0, "latent_image": ["5", 0], "model": ["4", 0], "negative": ["7", 0], "positive": ["6", 0], "sampler_name": "euler", "scheduler": "normal", "seed": 0, "steps": 20}},
    "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "flux1-dev-fp8.safetensors"}},
    "5": {"class_type": "EmptyLatentImage", "inputs": {"batch_size": 1, "height": 500, "width": 800}},
    "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["4", 1], "text": ""}},
    "7": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["4", 1], "text": ""}},
    "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
    "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "RPGEngine", "images": ["8", 0]}},
}

IMAGES = [
    {"name": "genre-adventure", "prompt": "epic adventure landscape, winding path through lush green valley toward distant mountains, ancient stone bridge over rushing river, warm golden sunlight, anime RPG key art, cel-shaded style, vivid saturated colors, heroic exploration mood"},
    {"name": "genre-dark-fantasy", "prompt": "dark enchanted forest with twisted trees, faint glowing runes on stone ruins, eerie mist, a lone torch flickering, dark fantasy RPG art, cel-shaded style, muted earth tones with purple highlights, foreboding atmospheric mood"},
    {"name": "genre-noir", "prompt": "rain-slicked city street at night, neon signs reflecting in puddles, lone figure in trenchcoat under streetlight, noir detective RPG art, cel-shaded style, high contrast shadows, moody cinematic atmosphere"},
]

def run():
    for img in IMAGES:
        path = os.path.join(OUTPUT_DIR, f"{img['name']}.png")
        if os.path.exists(path):
            print(f"[{img['name']}] Already exists, skipping")
            continue
        wf = json.loads(json.dumps(WORKFLOW_TEMPLATE))
        wf["6"]["inputs"]["text"] = img["prompt"]
        wf["3"]["inputs"]["seed"] = random.randint(0, 2**32)
        wf["9"]["inputs"]["filename_prefix"] = f"rpg_{img['name']}"
        payload = json.dumps({"prompt": wf}).encode()
        req = urllib.request.Request(f"{COMFYUI_URL}/prompt", data=payload, headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req)
        pid = json.loads(resp.read())["prompt_id"]
        print(f"[{img['name']}] Queued, waiting...")
        for _ in range(150):
            time.sleep(2)
            try:
                r = urllib.request.urlopen(f"{COMFYUI_URL}/history/{pid}")
                h = json.loads(r.read())
                if pid in h:
                    for nid, no in h[pid].get("outputs", {}).items():
                        if "images" in no:
                            fn = no["images"][0]["filename"]
                            sf = no["images"][0].get("subfolder", "")
                            urllib.request.urlretrieve(f"{COMFYUI_URL}/view?filename={fn}&subfolder={sf}&type=output", path)
                            print(f"[{img['name']}] Saved")
                            break
                    break
            except: pass
        else:
            print(f"[{img['name']}] TIMEOUT")

if __name__ == "__main__":
    run()
