# Model Strategy

Guide to which LLM models handle each role in the RPG Engine, optimization recommendations, fine-tuning plans, and NSFW capability analysis.

## Current Setup

| Role | Current Model | Provider | Notes |
|------|-------------|----------|-------|
| Creative (narrator, coda, book) | mythomax:13b | Ollama | 13B, uncensored RP, excellent prose |
| Dialogue (NPC) | same as above | Ollama | Works but overkill for 1-2 sentences |
| Classification (mood) | same as above | Ollama | Massive overkill for UP/DOWN/SAME |
| Summarization (condense) | same as above | Ollama | Works fine |
| AI Tools (improve, suggest, generate) | same as above (local) / gpt-4o-mini (VPS) | Ollama/Azure | |
| Portrait descriptions | same as above | Ollama | Visual description from personality |

**Default model:** `mythomax:13b`
**Status:** All roles use the same model. `/settings` page exists but roles aren't wired to LLM calls yet.

## Hardware

- **Desktop GPU:** NVIDIA RTX 5070 Ti (16GB VRAM)
- **VPS:** No GPU — uses Azure OpenAI (gpt-4o-mini)
- **ComfyUI:** Flux fp8 model for image generation (shares GPU with Ollama)

## NSFW Capability

The engine supports a wide range of story content including explicit/NSFW. Model selection must account for this — censored models will refuse or sanitize adult content.

### NSFW Model Tiers

**Tier 1 — Premium uncensored RP (12-13B, fits in 16GB VRAM):**

| Model | Size | NSFW | Quality | Notes |
|-------|------|------|---------|-------|
| **mythomax:13b** | 13B | ✅ Full | Excellent | Community RP favorite, great character consistency. **Current default.** |
| **lumimaid:12b** | 12B | ✅ Full | Excellent | Built specifically for explicit RP with emotional depth |
| **nchapman/mn-12b-mag-mell-r1** | 12.2B | ✅ Full | Good | Previous default. Magnum Naughty — purpose-built uncensored RP |
| **nous-hermes2:13b** | 13B | ✅ Yes | Good | Strong RP + instruction following. Uncensored but not NSFW-focused |

**Tier 2 — General uncensored (7-8B, faster):**

| Model | Size | NSFW | Quality | Notes |
|-------|------|------|---------|-------|
| **dolphin-llama3:8b** | 8B | ✅ Yes | Decent | Good all-rounder, uncensored. Installed. |
| **openhermes:7b** | 7B | ✅ Yes | Decent | Fast, follows instructions, no filters |
| **dolphin-mistral:latest** | 7B | ✅ Yes | Decent | Older dolphin variant. Installed. |

**Tier 3 — Censored (fine for non-NSFW roles):**

| Model | Size | NSFW | Use for |
|-------|------|------|---------|
| **llama3.2:3b** | 3B | ❌ No | Classification (mood UP/DOWN/SAME) — doesn't generate content |
| **llama3.2:1b** | 1.2B | ❌ No | Classification — tiny and fast |
| **phi3:mini** | 3.8B | ❌ No | Classification, summarization |
| **llama3.1:8b** | 8B | ❌ No | Summarization — doesn't need to write NSFW |

**Tier 4 — Large/cloud only:**

| Model | Size | NSFW | Notes |
|-------|------|------|-------|
| **dolphin-mixtral:8x7b** | 47B MoE | ✅ Yes | ~26GB, won't fit in 16GB |
| **dolphin-llama3:70b** | 70B | ✅ Yes | API only |
| **midnight-miqu:70b** | 70B | ✅ Full | Premium NSFW writing, API only |
| **mistral-small:24b** | 23.6B | ⚠️ Partial | Good prose but has some guardrails. Installed. |

### NSFW-Critical Roles

| Role | Needs NSFW? | Why |
|------|------------|-----|
| **Narrator** | ✅ Yes | Describes explicit scenes |
| **NPC Dialogue** | ✅ Yes | Characters may speak explicitly |
| **Narrator Coda** | ✅ Yes | Wraps up scenes that may be explicit |
| **Mood Classification** | ❌ No | Only outputs UP/DOWN/SAME |
| **Condense** | ⚠️ Maybe | Summarizes scenes — needs to not censor the summary |
| **AI Tools** | ❌ No | Story structure, not content |
| **Book prose** | ✅ Yes | Rewrites play sessions that may include explicit content |

### Installed Models — NSFW Assessment

| Model | NSFW | Installed |
|-------|------|-----------|
| mythomax:13b | ✅ Full | ✅ Yes (new default) |
| nchapman/mn-12b-mag-mell-r1:latest | ✅ Full | ✅ Yes |
| dolphin-llama3:8b | ✅ Yes | ✅ Yes |
| dolphin-mistral:latest | ✅ Yes | ✅ Yes |
| mistral-small:24b | ⚠️ Partial | ✅ Yes |
| deepseek-r1:14b | ❌ No | ✅ Yes |
| llama3.1:8b | ❌ No | ✅ Yes |
| llama3:latest | ❌ No | ✅ Yes |
| mistral:7b-instruct | ⚠️ Partial | ✅ Yes |
| qwen2.5-coder:7b | ❌ No | ✅ Yes |
| llama3.2:1b | ❌ No | ✅ Yes |
| gpt-oss:120b-cloud | ❓ Unknown | ✅ Yes |

## Role Requirements

### Classification (mood: UP/DOWN/SAME)
- **Input:** ~200 tokens
- **Output:** 1 word (UP, DOWN, or SAME)
- **Frequency:** Highest — per character × per axis × per turn
- **Needs:** Instruction following only
- **NSFW needed:** No
- **Optimal size:** 1-3B
- **Recommended:** `llama3.2:3b` or fine-tuned 1B classifier
- **Status:** ⬜ Not optimized

### Summarization (condense)
- **Input:** ~500 tokens (history + current turn)
- **Output:** ~100 words
- **Frequency:** Once per turn
- **Needs:** Comprehension, compression, length control
- **NSFW needed:** Maybe (shouldn't censor summaries of explicit scenes)
- **Optimal size:** 3-8B uncensored
- **Recommended:** `dolphin-llama3:8b` (uncensored + good at summarization)
- **Status:** ⬜ Not optimized

### Character Dialogue (NPC)
- **Input:** ~400 tokens (personality + scene + history)
- **Output:** 1-2 sentences
- **Frequency:** Once per character per turn
- **Needs:** Personality, voice consistency, creativity, NSFW capability
- **NSFW needed:** Yes
- **Optimal size:** 7-13B uncensored
- **Recommended:** `mythomax:13b` (default) or `dolphin-llama3:8b` for speed
- **Status:** ⬜ Not optimized

### Creative Writing (narrator, coda, book)
- **Input:** ~500-1000 tokens
- **Output:** 200-500 tokens (2-3 paragraphs)
- **Frequency:** 1-2 times per turn
- **Needs:** Prose quality, atmosphere, sensory detail, second person, NSFW capability
- **NSFW needed:** Yes
- **Optimal size:** 12B+ uncensored
- **Recommended:** `mythomax:13b` (default)
- **Status:** ✅ Using mythomax:13b

### AI Tools (improve, suggest, generate)
- **Input:** Varies
- **Output:** Structured (JSON, lists, replacement text)
- **Frequency:** On demand only
- **Needs:** Instruction following, JSON output
- **NSFW needed:** No
- **Optimal size:** 8B+ or cloud API
- **Recommended:** Azure `gpt-4o-mini` or `deepseek-r1:14b`
- **Status:** ⬜ Not optimized

## Models to Pull

| Model | Size | Why | Command | Priority |
|-------|------|-----|---------|----------|
| `llama3.2:3b` | 3B | Classification — fast, tiny | `ollama pull llama3.2:3b` | High |
| `lumimaid` | 12B | Alternative NSFW narrator — compare with mythomax | `ollama pull lumimaid` | Medium |
| `phi3:mini` | 3.8B | Classification + summarization | `ollama pull phi3:mini` | Medium |
| `gemma2:9b` | 9B | Dialogue balance option | `ollama pull gemma2:9b` | Low |
| `openhermes:7b` | 7B | Fast uncensored dialogue | `ollama pull openhermes` | Low |

## VRAM Management

16GB total. Ollama swaps models but switching takes 5-10 seconds.

### Option A: Two models (recommended)
- **mythomax:13b** for creative + dialogue + condense (~8-9GB)
- **llama3.2:3b** for classification (~2GB)
- Leaves ~5GB for system/ComfyUI
- **Total LLM VRAM:** ~11GB

### Option B: Three-tier (optimal speed)
- **mythomax:13b** for creative writing only (~8-9GB)
- **dolphin-llama3:8b** for dialogue + condense (~5GB)
- **llama3.2:3b** for classification (~2GB)
- ⚠️ Only works if Ollama swaps efficiently — can't all be loaded at once

### Option C: Cloud hybrid
- **mythomax:13b local** for creative + dialogue (latency-sensitive, NSFW-capable)
- **Azure gpt-4o-mini** for tools, classification (not latency-sensitive, no NSFW needed)
- Best of both — local uncensored quality for gameplay, cloud for background tasks

## Fine-Tuning Roadmap

### Phase 1: Mood Classifier (highest ROI)
- **Base model:** llama3.2:1b or 3b (censored fine for classification)
- **Training data:** 500+ examples of (scene + character + axis → UP/DOWN/SAME)
- **Method:** LoRA fine-tune with unsloth
- **Expected result:** Near-instant, 99% accurate mood classification
- **Status:** ⬜ Not started

### Phase 2: RPG Narrator (NSFW)
- **Base model:** mythomax:13b or dolphin-llama3:8b
- **Training data:** Examples of good second-person RPG narration across genres (including explicit)
- **Method:** LoRA fine-tune
- **Expected result:** More consistent style, better scene pacing, genre-appropriate tone
- **Status:** ⬜ Not started

### Phase 3: Character Voice LoRAs (NSFW)
- **Base model:** mythomax:13b or dolphin-llama3:8b
- **Training data:** Per-archetype dialogue examples
- **Method:** Separate LoRA per character archetype
- **Archetypes:** gruff old man, seductive, dominant, submissive, nervous, confident, playful, threatening
- **Expected result:** Consistent, distinct character voices across all content types
- **Status:** ⬜ Not started

### Phase 4: Genre-Specific LoRAs
- **Base model:** mythomax:13b
- **Training data:** Genre-specific narration samples
- **Genres:** gothic horror, romance, sci-fi erotica, dark fantasy, comedy, thriller
- **Expected result:** Swap LoRA based on story genre for genre-appropriate prose
- **Status:** ⬜ Not started

### Fine-Tuning Setup
- **Tool:** unsloth (fast LoRA training)
- **Hardware:** RTX 5070 Ti (sufficient for up to 13B LoRA fine-tuning)
- **Training time:** 30min-2hrs per fine-tune
- **Status:** ⬜ Not installed

## Implementation Progress

### Infrastructure
- [x] `/models` endpoint — lists available models from all providers
- [x] `/settings` page — role-based model selection UI
- [x] `model_settings.json` — persists role defaults
- [x] `get_model_for_role()` helper function
- [x] Switch default model to mythomax:13b
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
- [ ] Pull `lumimaid` and compare with mythomax for narrator quality
- [ ] Benchmark: response time per model per role
- [ ] Set up unsloth for fine-tuning
- [ ] Create mood classifier training dataset
- [ ] Fine-tune mood classifier
- [ ] Test fine-tuned classifier in production

## Benchmarks

*(To be filled in as we test)*

| Role | Model | Avg Response Time | Quality | NSFW Quality | Notes |
|------|-------|-------------------|---------|-------------|-------|
| Narrator | mn-12b (previous) | ? | ? | ? | Previous default |
| Narrator | mythomax:13b | ? | ? | ? | New default |
| NPC | mythomax:13b | ? | ? | ? | |
| Classification | mythomax:13b | ? | ? | N/A | Baseline |
| Classification | llama3.2:3b | ? | ? | N/A | |
| Classification | llama3.2:1b | ? | ? | N/A | |
| Condense | mythomax:13b | ? | ? | ? | |
