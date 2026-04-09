# Image Asset Backlog

This is a generation-ready asset list for improving visual polish across the site.

Style baseline for all prompts:
- bright anime RPG concept art
- cel-shaded look
- vivid, cheerful palette
- readable composition (clear subject, low clutter)
- no text/watermarks/logos

## Priority 0 - Already completed previews

These are done and approved as style anchors:

- `web/static/images/hero.png`
- `web/static/images/login-bg.png`
- `web/static/images/genre-fantasy.png`
- `web/static/images/genre-mystery.png`

## Priority 1 - Core static pack (high impact)

### Genre fallback set (finish remaining 12)

These are used in story cards when no custom cover exists.

| Filename | Size | Prompt starter |
|---|---:|---|
| `web/static/images/genre-sci-fi.png` | 800x500 | futuristic city skyline, neon sky, anime RPG background, bright energetic palette |
| `web/static/images/genre-horror.png` | 800x500 | haunted forest with stylized spirits, spooky but colorful, anime RPG, playful eerie mood |
| `web/static/images/genre-romance.png` | 800x500 | sunset garden with petals and lanterns, warm romantic anime RPG scene |
| `web/static/images/genre-thriller.png` | 800x500 | rooftop chase at golden hour, dynamic action framing, anime RPG |
| `web/static/images/genre-slice-of-life.png` | 800x500 | cozy town street market, daytime, friendly anime RPG ambiance |
| `web/static/images/genre-historical.png` | 800x500 | vibrant old city square, period costumes, anime RPG style |
| `web/static/images/genre-supernatural.png` | 800x500 | magical shrine with spirit lights, bright mystical anime RPG scene |
| `web/static/images/genre-post-apocalyptic.png` | 800x500 | reclaimed ruins with greenery, hopeful survivor camp, anime RPG |
| `web/static/images/genre-urban-fantasy.png` | 800x500 | modern city with visible magic sigils, twilight glow, anime RPG |
| `web/static/images/genre-erotica.png` | 800x500 | elegant candlelit lounge, intimate but tasteful atmosphere, anime illustration |
| `web/static/images/genre-drama.png` | 800x500 | stage-lit emotional confrontation, expressive anime RPG composition |
| `web/static/images/genre-comedy.png` | 800x500 | lively tavern festival, chibi accents, colorful anime RPG fun |

### Lobby and empty-state visuals

| Filename | Size | Route usage | Prompt starter |
|---|---:|---|---|
| `web/static/images/site/empty-stories.png` | 1024x640 | `/stories`, lobby empty cards | cheerful adventurer at quest board, anime RPG, "start your story" vibe |
| `web/static/images/site/empty-books.png` | 1024x640 | `/books` empty state | magical library desk with blank book glowing, anime RPG |
| `web/static/images/site/empty-playback.png` | 1024x640 | `/playback` pre-run state | strategy desk with notes and crystal monitor, anime RPG analytics mood |

## Priority 2 - Docs and utility visuals

### Docs section hero images

| Filename | Size | Route usage | Prompt starter |
|---|---:|---|---|
| `web/static/images/docs/playing-hero.png` | 1280x480 | `/docs/playing` | party exploring bright ruins, anime RPG play guide hero |
| `web/static/images/docs/stories-hero.png` | 1280x480 | `/docs/stories` | writer crafting quest map with magical pen, anime RPG creator hero |
| `web/static/images/docs/engine-hero.png` | 1280x480 | `/docs/engine` | stylized node graph hologram in fantasy lab, anime RPG systems art |

### Graph and settings visuals

| Filename | Size | Route usage | Prompt starter |
|---|---:|---|---|
| `web/static/images/site/graph-empty.png` | 1024x640 | `/graphs` empty states | clean node map blueprint on table, anime tech-fantasy |
| `web/static/images/site/settings-models.png` | 1024x640 | `/settings` header card | mage selecting glowing model orbs from a shelf, anime RPG |

## Priority 3 - Micro-asset icon pack

Use transparent PNGs (or SVG later) to support badges/chips/cards.

| Filename | Size | Intended use |
|---|---:|---|
| `web/static/images/icons/node-ok.png` | 256x256 | Node Health status icon |
| `web/static/images/icons/node-warn.png` | 256x256 | Node Health warning |
| `web/static/images/icons/node-error.png` | 256x256 | Node Health error |
| `web/static/images/icons/mood-up.png` | 256x256 | mood increase indicator |
| `web/static/images/icons/mood-down.png` | 256x256 | mood decrease indicator |
| `web/static/images/icons/mood-same.png` | 256x256 | mood stable indicator |

## Batch generation plan

1. **Batch A (fast win)**  
   Generate all remaining `genre-*.png` files.
2. **Batch B (empty states)**  
   Generate `empty-*.png` assets for stories/books/playback.
3. **Batch C (docs heroes)**  
   Generate `docs/*-hero.png`.
4. **Batch D (utility/art accents)**  
   Graph/settings and icon pack.

## Naming and consistency rules

- Keep deterministic, human-readable names.
- Do not overwrite user-generated story cover/portrait/scene images.
- Keep static site assets under:
  - `web/static/images/` for legacy referenced files
  - `web/static/images/site/` for generic UI artwork
  - `web/static/images/docs/` for docs headers
  - `web/static/images/icons/` for iconography

## Implementation note

Current routes already consume:
- `hero.png`, `login-bg.png`
- `genre-{genre}.png`

As new assets are generated, wire them incrementally into:
- empty states
- docs section headers
- graph/settings headers

Prefer shipping in small visual PR-sized chunks to keep review simple.
