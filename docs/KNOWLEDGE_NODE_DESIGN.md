# Knowledge Node — RAG-Powered Character Expertise

## Overview

A generic RAG (Retrieval Augmented Generation) node that gives any character access to any document library. The story author configures what knowledge is available and who can access it. One node, unlimited use cases.

## Architecture

```
Player says something
    ↓
knowledge node embeds the turn text (player message + narrator text)
    ↓
Searches configured collections for relevant chunks
    ↓
Writes _knowledge to state: { "character_key": [...relevant chunks...] }
    ↓
character_agent sees the chunks and references them naturally
```

### Tech Stack

| Component | Tool | Status |
|---|---|---|
| Embedding model | `nomic-embed-text` via Ollama | Already installed |
| Vector store | ChromaDB (local, no API keys) | Needs `pip install chromadb` |
| Document sources | PDFs, text files, manual entries | Per story |
| Node | `nodes/knowledge.py` | To build |

## Story Configuration

### Per-Character Knowledge

```json
{
  "characters": {
    "therapist": {
      "prompt": "You are Dr. Elaine Ward...",
      "knowledge": {
        "collections": ["cbt_techniques", "dsm5_anxiety"],
        "max_results": 3,
        "min_relevance": 0.65,
        "cooldown_turns": 3,
        "instruction": "Reference techniques naturally when relevant. Don't lecture or list — weave them into your therapeutic approach."
      }
    }
  }
}
```

### Stage-Aware Filtering (with progression node)

```json
{
  "knowledge": {
    "collections": ["cbt_techniques"],
    "max_results": 3,
    "stage_filter": {
      "resistance": ["rapport_building", "active_listening"],
      "surface": ["thought_records", "cognitive_distortions"],
      "breakthrough": ["trauma_processing", "emdr_basics"]
    }
  }
}
```

### Narrator Knowledge (optional)

```json
{
  "narrator_knowledge": {
    "collections": ["courtroom_layout", "legal_procedure"],
    "max_results": 1,
    "instruction": "Use for procedural accuracy in scene descriptions"
  }
}
```

## Example Use Cases

### Courtroom / Legal Drama

```json
{
  "prosecutor": {
    "knowledge": {
      "collections": ["federal_evidence_rules", "state_criminal_code", "landmark_cases"],
      "max_results": 3,
      "instruction": "Cite specific statutes and case law when questioning. Use them to support your arguments."
    }
  },
  "judge": {
    "knowledge": {
      "collections": ["federal_evidence_rules", "courtroom_procedure"],
      "max_results": 2,
      "instruction": "Reference the specific rule when sustaining or overruling objections."
    }
  }
}
```

### Therapy / Mental Health

```json
{
  "therapist": {
    "knowledge": {
      "collections": ["cbt_techniques", "dsm5_criteria", "therapeutic_frameworks"],
      "max_results": 3,
      "instruction": "Reference techniques naturally when relevant. Don't lecture."
    }
  }
}
```

### Fantasy / World Lore

```json
{
  "sage": {
    "knowledge": {
      "collections": ["world_lore", "magic_system", "faction_history"],
      "max_results": 2,
      "instruction": "You have studied the ancient texts. Share what you know when asked, but speak as a scholar, not a textbook."
    }
  }
}
```

### Other Use Cases

| Story type | RAG collections |
|---|---|
| Medical drama | Drug interactions, diagnostic criteria, treatment protocols |
| Sci-fi | Ship technical manuals, species databases, regulations |
| Historical fiction | Period customs, real events, historical figures |
| Corporate thriller | SEC regulations, financial rules, compliance |
| Military | Rules of engagement, rank structure, tactical doctrine |
| Cooking competition | Recipes, technique descriptions, food science |
| Tabletop RPG | Rulebook, bestiary, spell lists |
| Survival | Plant ID, animal behavior, wilderness medicine |
| Education | Curriculum content, textbook material, exercises |

## What the Character Agent Sees

When the knowledge node finds relevant chunks, the character_agent prompt gets an extra block:

```
REFERENCE MATERIAL (use naturally, don't lecture):
---
[1] Cognitive Restructuring: When a patient presents with rumination
or catastrophizing, guide them to identify the automatic thought,
examine the evidence for and against it, and generate a balanced
alternative thought...
---
[2] Sleep Hygiene for Anxiety: Racing thoughts at bedtime often
respond to a "worry window" technique — designate 15 minutes
earlier in the evening to write down worries...
---
```

## Document Ingestion

### File Upload

```
POST /api/knowledge/ingest
{
  "collection": "cbt_techniques",
  "file": "cbt_handbook.pdf",
  "chunk_size": 400,
  "overlap": 50
}
```

### Directory Scan

```
POST /api/knowledge/ingest-directory
{
  "collection": "federal_evidence_rules",
  "path": "rag_documents/evidence_rules/",
  "chunk_size": 500
}
```

### Manual Entries

```
POST /api/knowledge/add
{
  "collection": "cbt_techniques",
  "entries": [
    {
      "title": "Thought Record",
      "content": "A thought record is a CBT worksheet that helps patients identify and challenge automatic negative thoughts..."
    },
    {
      "title": "Worry Window",
      "content": "The worry window technique involves scheduling a specific 15-minute period..."
    }
  ]
}
```

## Embedding Pipeline

```
Document → Split into chunks (400-500 tokens each)
    ↓
Each chunk → nomic-embed-text (local Ollama) → 768-dim vector
    ↓
Store in ChromaDB: { id, text, embedding, metadata: {source, title, collection} }
```

At query time:

```
Turn text → nomic-embed-text → query vector
    ↓
ChromaDB similarity search → top N chunks
    ↓
Return as text blocks to inject into character prompts
```

## Relevance Filtering

- **Similarity threshold** — Only return chunks above min_relevance (e.g., 0.65). Below that, return nothing — character responds normally.
- **Cooldown** — Don't cite the same chunk twice within N turns. Prevents repetition.
- **Stage awareness** — Connected to progression node, query can filter by current stage. Early therapy retrieves rapport techniques, not trauma processing.

## When RAG vs. When LLM Already Knows

RAG is for:

- **Specificity** — Not "CBT helps" but the exact steps of a thought record worksheet
- **Consistency** — Every playthrough references the same lore, not whatever the LLM invents
- **Accuracy** — Real statute numbers, real case citations, real drug interactions
- **Custom content** — Your world, your rules, your characters' histories
- **Authority** — The character speaks from a source, not from vibes

## Node Implementation Sketch

```python
def knowledge_node(state: dict) -> dict:
    """Retrieve relevant knowledge for characters that have knowledge config."""
    characters = state.get("characters") or {}
    narrator_text = state.get("_narrator_text") or ""
    message = state.get("message") or ""

    query_text = f"{message} {narrator_text}"

    knowledge = {}
    for char_key, char in characters.items():
        config = char.get("knowledge")
        if not config:
            continue
        chunks = search_collections(
            query_text,
            config["collections"],
            max_results=config.get("max_results", 3),
            min_relevance=config.get("min_relevance", 0.65)
        )
        if chunks:
            knowledge[char_key] = {
                "chunks": chunks,
                "instruction": config.get("instruction", "")
            }

    return {"_knowledge": knowledge} if knowledge else {}
```

## Pipeline Position

```
narrator → character_agent → response_builder → mood →
knowledge → progression → expression_picker → scene_image →
condense → memory
```

Or in a knowledge-heavy story:

```
knowledge → narrator → character_agent → response_builder →
mood → condense → memory
```

(Knowledge before narrator so the narrator can also reference material for procedural accuracy.)

## Dependencies

- `pip install chromadb`
- `nomic-embed-text` model in Ollama (already available)
- New Flask routes for ingestion
- New `nodes/knowledge.py`
- Updates to `character_agent.py` to read `_knowledge`
- Optional updates to `narrator.py` for narrator-level knowledge
