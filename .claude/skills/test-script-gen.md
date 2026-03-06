Test the script generation endpoint across all three input sources (text, voice, preset).

Choose which source to test or run all three sequentially.

---

## Source 1: TEXT (fastest, no audio needed)

```bash
PROJECT=$(python3 -c "import uuid; print(uuid.uuid4())")
echo "Project: $PROJECT"

curl -s -X POST http://localhost:8000/api/v1/projects/$PROJECT/generate-script \
  -H 'Content-Type: application/json' \
  -d '{
    "source": "text",
    "transcript": "The hidden reason why most people fail at building habits is not willpower — it is their environment. Change your space before you try to change yourself.",
    "target_platforms": ["instagram_reels"],
    "style": "modern_energetic",
    "video_duration": 30,
    "art_style": "cinematic",
    "caption_style": "bold_stroke",
    "background_music": "none",
    "video_format": "storytelling"
  }' | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('quality_score:', d.get('metadata',{}).get('agent_quality_score','n/a'))
print('hook:', d.get('hook',{}).get('text',''))
print('scenes:', len(d.get('scenes',[])))
for s in d.get('scenes',[]):
    print(f'  scene {s[\"scene_id\"]} [{s.get(\"duration_seconds\")}s]: {s.get(\"voiceover_text\",\"\")[:80]}')
print('cta:', d.get('cta',{}).get('text',''))
"
```

---

## Source 2: PRESET (uses Reddit trending context)

```bash
PROJECT=$(python3 -c "import uuid; print(uuid.uuid4())")
echo "Project: $PROJECT"

curl -s -X POST http://localhost:8000/api/v1/projects/$PROJECT/generate-script \
  -H 'Content-Type: application/json' \
  -d '{
    "source": "preset",
    "preset": "stoic_motivation",
    "topic_hint": "why Marcus Aurelius would delete social media",
    "target_platforms": ["youtube_shorts"],
    "style": "dramatic",
    "video_duration": 30,
    "art_style": "cinematic",
    "caption_style": "beast",
    "background_music": "quiet_before_storm",
    "video_format": "storytelling"
  }' | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('quality_score:', d.get('metadata',{}).get('agent_quality_score','n/a'))
print('hook:', d.get('hook',{}).get('text',''))
print('scenes:', len(d.get('scenes',[])))
for s in d.get('scenes',[]):
    print(f'  scene {s[\"scene_id\"]} [{s.get(\"duration_seconds\")}s]: {s.get(\"voiceover_text\",\"\")[:80]}')
print('cta:', d.get('cta',{}).get('text',''))
"
```

---

## Source 3: SCARY STORIES preset (matches manual_test.py)

```bash
cd backend && python manual_test.py 2>&1 | head -60
```

---

## Check script quality score only (quick)

```bash
PROJECT=$(python3 -c "import uuid; print(uuid.uuid4())")
curl -s -X POST http://localhost:8000/api/v1/projects/$PROJECT/generate-script \
  -H 'Content-Type: application/json' \
  -d '{"source":"text","transcript":"Morning routines for productivity","target_platforms":["tiktok"],"style":"modern_energetic","video_duration":15,"art_style":"realism","caption_style":"sleek","background_music":"none"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('score:', d.get('metadata',{}).get('agent_quality_score')); print('hook:', d.get('hook',{}).get('text','')[:100])"
```
