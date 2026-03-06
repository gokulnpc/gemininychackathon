Add a new creative mode to the Creative Director feature.

Steps to add a new mode (e.g. "podcast_promo"):

1. **Add the enum value** in `backend/models/schemas.py`:
   ```python
   class CreativeMode(str, Enum):
       ...
       podcast_promo = "podcast_promo"   # ← new
   ```

2. **Add the mode prompt** in `backend/services/gemini_interleaved.py` inside `_MODE_PROMPTS`:
   ```python
   "podcast_promo": (
       "You are a podcast marketing expert. Generate a complete promotional package.\n\n"
       "Produce:\n"
       "1. Write a compelling episode title and teaser (2 sentences).\n"
       "2. Generate a podcast cover art image.\n"
       "3. Write show notes (3-4 sentences summarising key takeaways).\n"
       "4. Generate a quote card image with the best pull-quote.\n"
       "5. Write 10-15 hashtags.\n\n"
       "Tone: conversational, curiosity-driven, shareable."
   ),
   ```

3. **No router changes needed** — `CreativeMode` enum is auto-validated by FastAPI.

4. **Test it**:
   ```bash
   curl -X POST http://localhost:8000/api/v1/creative-director/generate \
     -H 'Content-Type: application/json' \
     -d '{"brief":"Interview with a quantum computing researcher","mode":"podcast_promo"}'
   ```

5. **Update `.claude/CLAUDE.md`** — add the new mode to the Phase 3 mode table.
