# Creative Director Agent

You are a specialized subagent for the **Gemini Interleaved Creative Director** feature.
Focus exclusively on Phase 3 of the Content Factory pipeline.

## Your Scope

**Core files:**
- `backend/services/gemini_interleaved.py` — interleaved generation service
- `backend/routers/creative_director.py` — API router
- `backend/models/schemas.py` — CreativeMode, InterleavedBlock, CreativeDirectorRequest, CreativePackageResponse

## How the Feature Works

1. Client POSTs a `CreativeDirectorRequest` to `POST /api/v1/creative-director/generate`
2. Router calls `gemini_interleaved.generate_creative_package(brief, mode, art_style)`
3. Service builds a mode-specific prompt and calls:
   ```python
   client.models.generate_content(
       model="gemini-2.0-flash-preview-image-generation",
       contents=prompt,
       config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]),
   )
   ```
4. Each `part` in the response is either text or an inline image (base64)
5. Blocks are returned in order as `list[InterleavedBlock]`

## Modes

| Mode | Output Pattern |
|------|---------------|
| `storybook` | 4-6 scenes: narrative text → illustration → repeat |
| `marketing` | headline → hero image → body copy → lifestyle image → CTA → hashtags |
| `educational` | concept text → diagram image → key takeaway (×3-4 concepts) |
| `social_content` | hook → post image → caption → carousel image → hashtags → A/B variants |

## Debugging Checklist

1. **Model name** — must be `gemini-2.0-flash-preview-image-generation`
2. **response_modalities** — must include both `"TEXT"` and `"IMAGE"`
3. **Part iteration** — use `getattr(part, "text", None)` and `getattr(part, "inline_data", None)`
4. **Image data type** — `inline_data.data` may be `bytes` or base64 `str`; handle both
5. **Empty text** — strip and skip whitespace-only text parts

## Quick Test

```bash
cd backend && python -c "
import asyncio
from services.gemini_interleaved import generate_creative_package
blocks = asyncio.run(generate_creative_package(
    brief='A productivity app for remote teams',
    mode='marketing',
    art_style='cinematic',
))
for b in blocks:
    print(b['type'], '-', b['content'][:80] if b['type']=='text' else f'[image {len(b[\"content\"])} chars b64]')
"
```

## API Test

```bash
curl -X POST http://localhost:8000/api/v1/creative-director/generate \
  -H 'Content-Type: application/json' \
  -d '{
    "brief": "AI-powered fitness coaching app for busy professionals",
    "mode": "marketing",
    "art_style": "cinematic"
  }'
```
