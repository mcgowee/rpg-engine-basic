---
name: comfyui
description: >
  Generate images using ComfyUI on the GPU desktop. Use when the user asks to
  generate, create, draw, or imagine an image. Trigger on words like "generate",
  "imagine", "draw", "create an image", "make a picture", etc.
user-invocable: true
---

# ComfyUI Image Generation

## How to use

Call `/api/imagine` on the LangGraph service. Always save the result to the workspace
before sending — WhatsApp requires files under the workspace directory.

```bash
curl -s -X POST http://127.0.0.1:5050/api/imagine \
  -H "Content-Type: application/json" \
  -d '{"prompt": "PROMPT_HERE", "negative": "", "width": 1024, "height": 1024, "steps": 20}'
```

## Parameters

| Field | Default | Notes |
|---|---|---|
| prompt | required | The image description |
| negative | "" | Things to avoid |
| model | flux1-dev-fp8.safetensors | See models below |
| width | 1024 | Pixels |
| height | 1024 | Pixels (use 576 for widescreen) |
| steps | 20 | More = slower + sharper |
| seed | -1 (random) | Pin for reproducibility |

## Available models

- `flux1-dev-fp8.safetensors` — default, best quality, photorealistic
- `getphatFLUXReality_v11Softcore.safetensors` — FLUX reality variant
- `juggernautXL_v8Rundiffusion.safetensors` — SDXL, good for people/LoRA
- `ponyDiffusionV6XL.safetensors` — SDXL variant

## LoRAs

### alex_lora.safetensors
- Trained on male images of alexchar
- **Always include** `man, male` in prompt and `woman, female, feminine` in negative
- Trigger word: `alexchar`
- Default strength: 0.85 (bump to 0.9 for stronger likeness)
- Default model: juggernautXL_v8Rundiffusion.safetensors
- Default steps: 30

**Default prompt structure:**
```
"alexchar, man, <scene description>, detailed face, cinematic, male"
```
**Default negative:**
```
"deformed, ugly, blurry, bad anatomy, extra limbs, watermark, woman, female, feminine"
```

**Example call:**
```bash
curl -s -X POST http://127.0.0.1:5050/api/imagine \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "alexchar, man, <scene>, detailed face, cinematic, male",
    "negative": "deformed, ugly, blurry, bad anatomy, extra limbs, watermark, woman, female, feminine",
    "lora": "alex_lora.safetensors",
    "lora_strength": 0.85,
    "width": 1024,
    "height": 768
  }'
```

## After generation

1. Copy image to workspace: `cp /tmp/... ~/.openclaw/workspace/last_imagine.png`
2. Send via WhatsApp message tool using the workspace path
3. Include the prompt and model in the caption

## Response shape

```json
{
  "prompt_id": "uuid",
  "filename": "sage_imagine_00001_.png",
  "image_url": "http://192.168.50.90:8188/view?...",
  "seed": 1234567890,
  "model": "flux1-dev-fp8.safetensors"
}
```

## Aspect ratios

- Square: 1024×1024
- Widescreen: 1024×576
- Portrait: 768×1024
- Tall: 576×1024
