# Model Strategy

Guide to which LLM models handle each role in the RPG Engine, optimization recommendations, and fine-tuning plans.

## Current Setup

| Role | Current Model | Provider | Notes |
|------|-------------|----------|-------|
| Creative (narrator, coda, book) | nchapman/mn-12b-mag-mell-r1:latest | Ollama | 12.2B, RP-focused, good prose |
| Dialogue (NPC) | same as above | Ollama | Works but overkill for 1-2 sentences |
| Classification (mood) | same as above | Ollama | Massive overkill for UP/DOWN/SAME |
| Summarization (condense) | same as above | Ollama | Works fine |
| AI Tools (improve, suggest, generate) | same as above (local) / gpt-4o-mini (VPS) | Ollama/Azure | |
| Portrait descriptions | same as above | Ollama | Visual description from personality |

**Status:** All roles use the same model. `/settings` page exists but roles aren't wired to LLM calls yet.

## Hardware

- **Desktop GPU:** NVIDIA RTX 5070 Ti (16GB VRAM)
- **VPS:** No GPU — uses Azure OpenAI (gpt-4o-mini)
- **ComfyUI:** Flux fp8 model for image generation (shares GPU with Ollama)

## Role Requirements

### Classification (mood: UP/DOWN/SAME)
- **Input:** ~200 tokens
- **Output:** 1 word (UP, DOWN, or SAME)
- **Frequency:** Highest — per character × per axis × per turn
- **Needs:** Instruction following only
- **Optimal size:** 1-3B
- **Recommended:** `llama3.2:3b` or fine-tuned 1B classifier
- **Status:** ⬜ Not optimized

### Summarization (condense)
- **Input:** ~500 tokens (history + current turn)
- **Output:** ~100 words
- **Frequency:** Once per turn
- **Needs:** Comprehension, compression, length control
- **Optimal size:** 3-8B
- **Recommended:** `phi-3:mini` (3.8B) or `llama3.1:8b`
- **Status:** ⬜ Not optimized

### Character Dialogue (NPC)
- **Input:** ~400 tokens (personality + scene + history)
- **Output:** 1-2 sentences
- **Frequency:** Once per character per turn
- **Needs:** Personality, voice consistency, creativity
- **Optimal size:** 7-12B
- **Recommended:** `dolphin-llama3:8b` (uncensored RP) or current 12B
- **Status:** ⬜ Not optimized

### Creative Writing (narrator, coda, book)
- **Input:** ~500-1000 tokens
- **Output:** 200-500 tokens (2-3 paragraphs)
- **Frequency:** 1-2 times per turn
- **Needs:** Prose quality, atmosphere, sensory detail, second person
- **Optimal size:** 12B+ (prose quality scales with size)
- **Recommended:** Current 12B or `mistral-small:24b` for premium quality
- **Status:** ✅ Already using best available (12B)

### AI Tools (improve, suggest, generate)
- **Input:** Varies
- **Output:** Structured (JSON, lists, replacement text)
- **Frequency:** On demand only
- **Needs:** Instruction following, JSON output
- **Optimal size:** 8B+ or cloud API
- **Recommended:** Azure `gpt-4o-mini` or `deepseek-r1:14b`
- **Status:** ⬜ Not optimized

## Available Models (Ollama - Installed)

| Model | Size | Family | Quantization | Best for |
|-------|------|--------|-------------|----------|
| nchapman/mn-12b-mag-mell-r1:latest | 12.2B | llama | Q4_K_M | Creative, dialogue (current default) |
| deepseek-r1:14b | 14.8B | qwen2 | Q4_K_M | Reasoning, tools |
| mistral-small:24b | 23.6B | llama | Q4_K_M | Premium creative writing |
| dolphin-llama3:8b | 8B | llama | Q4_0 | RP dialogue, uncensored |
| dolphin-mistral:latest | 7B | llama | Q4_0 | Dialogue, summarization |
| llama3.1:8b | 8.0B | llama | Q4_K_M | General purpose |
| llama3:latest | 8.0B | llama | Q4_0 | General purpose |
| mistral:7b-instruct | 7.2B | llama | Q4_K_M | Instruction following |
| qwen2.5-coder:7b | 7.6B | qwen2 | Q4_K_M | Code (not useful for RPG) |
| llama3.2:1b | 1.2B | llama | Q8_0 | Classification (tiny, fast) |
| gpt-oss:120b-cloud | 116.8B | gptoss | MXFP4 | Cloud inference only |

## Models to Pull

| Model | Size | Why | Command |
|-------|------|-----|---------|
| `llama3.2:3b` | 3B | Sweet spot for classification + simple tasks | `ollama pull llama3.2:3b` |
| `phi3:mini` | 3.8B | Microsoft's small model, great instruction following | `ollama pull phi3:mini` |
| `gemma2:9b` | 9B | Google's model, good dialogue balance | `ollama pull gemma2:9b` |

## VRAM Management

16GB total. Ollama swaps models but switching takes 5-10 seconds.

### Option A: Two models (simple)
- **12B** for creative + dialogue + summarization (~8GB)
- **1-3B** for classification (~1-2GB)
- Leaves ~6GB for system/ComfyUI
- **Total LLM VRAM:** ~10GB

### Option B: Three-tier (optimal)
- **12B** for creative writing only (~8GB)
- **7-8B** for dialogue + summarization (~5GB)
- **1-3B** for classification (~1-2GB)
- ⚠️ Only works if Ollama swaps efficiently — can't all be loaded at once

### Option C: Cloud hybrid
- **12B local** for creative + dialogue (latency-sensitive)
- **Azure gpt-4o-mini** for tools, summarization (not latency-sensitive)
- **1-3B local** for classification
- Best of both — local quality for gameplay, cloud for background tasks

## Fine-Tuning Roadmap

### Phase 1: Mood Classifier (highest ROI)
- **Base model:** llama3.2:1b or 3b
- **Training data:** 500+ examples of (scene + character + axis → UP/DOWN/SAME)
- **Method:** LoRA fine-tune with unsloth
- **Expected result:** Near-instant, 99% accurate mood classification
- **Status:** ⬜ Not started

### Phase 2: RPG Narrator
- **Base model:** llama3.1:8b or mistral:7b
- **Training data:** Examples of good second-person RPG narration
- **Method:** LoRA fine-tune
- **Expected result:** 7B model writes like a 12B for this specific style
- **Status:** ⬜ Not started

### Phase 3: Character Voice LoRAs
- **Base model:** dolphin-llama3:8b
- **Training data:** Per-character dialogue examples
- **Method:** Separate LoRA per character archetype (gruff old man, nervous suspect, etc.)
- **Expected result:** Consistent, distinct character voices
- **Status:** ⬜ Not started

### Fine-Tuning Setup
- **Tool:** unsloth (fast LoRA training)
- **Hardware:** RTX 5070 Ti (sufficient for 1-8B fine-tuning)
- **Training time:** 30min-2hrs per fine-tune
- **Status:** ⬜ Not installed

## Implementation Progress

### Infrastructure
- [x] `/models` endpoint — lists available models from all providers
- [x] `/settings` page — role-based model selection UI
- [x] `model_settings.json` — persists role defaults
- [x] `get_model_for_role()` helper function
- [ ] Wire classification calls to role setting
- [ ] Wire summarization calls to role setting
- [ ] Wire dialogue calls to role setting
- [ ] Wire creative calls to role setting
- [ ] Wire AI tools calls to role setting
- [ ] Per-story model overrides (Models tab in story editor)
- [ ] Per-character model overrides (in character settings)

### Model Optimization
- [ ] Pull `llama3.2:3b` for classification testing
- [ ] Test mood classification with 3B model
- [ ] Test mood classification with 1B model
- [ ] Benchmark: response time per model per role
- [ ] Set up unsloth for fine-tuning
- [ ] Create mood classifier training dataset
- [ ] Fine-tune mood classifier
- [ ] Test fine-tuned classifier in production

## Benchmarks

*(To be filled in as we test)*

| Role | Model | Avg Response Time | Quality | Notes |
|------|-------|-------------------|---------|-------|
| Classification | mn-12b (current) | ? | ? | Baseline |
| Classification | llama3.2:1b | ? | ? | |
| Classification | llama3.2:3b | ? | ? | |
| Narrator | mn-12b (current) | ? | ? | Baseline |
| NPC | mn-12b (current) | ? | ? | Baseline |
| Condense | mn-12b (current) | ? | ? | Baseline |
