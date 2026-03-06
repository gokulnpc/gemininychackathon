Run the full end-to-end pipeline: Phase 1 (script) → Phase 2 (video).

This mirrors `backend/manual_test.py` but lets you customise the brief inline.

---

## Quick E2E — text source, shortest video (fastest, ~3–6 min)

```bash
PROJECT=$(python3 -c "import uuid; print(uuid.uuid4())")
echo "=== Project: $PROJECT ==="

# Phase 1: Script
echo "--- Phase 1: Generate Script ---"
SCRIPT=$(curl -s -X POST http://localhost:8000/api/v1/projects/$PROJECT/generate-script \
  -H 'Content-Type: application/json' \
  -d '{
    "source": "text",
    "transcript": "Stop letting notifications steal your focus. The average person checks their phone 96 times a day. Here is the 3-step system to take back your attention.",
    "target_platforms": ["instagram_reels"],
    "style": "modern_energetic",
    "video_duration": 15,
    "art_style": "cinematic",
    "caption_style": "bold_stroke",
    "background_music": "none"
  }')

echo "$SCRIPT" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('score:', d.get('metadata',{}).get('agent_quality_score'))
print('hook:', d.get('hook',{}).get('text','')[:100])
print('scenes:', len(d.get('scenes',[])))
"

# Phase 2: Video (pass full script back)
echo "--- Phase 2: Generate Video ---"
VIDEO_PAYLOAD=$(echo "$SCRIPT" | python3 -c "
import sys, json
script = json.load(sys.stdin)
payload = {
  'script': script,
  'target_platforms': ['instagram_reels'],
  'caption_style': 'bold_stroke',
  'video_duration': 15,
  'art_style_override': 'cinematic',
  'music_preset_override': 'none'
}
print(json.dumps(payload))
")

curl -s -X POST http://localhost:8000/api/v1/projects/$PROJECT/generate-video \
  -H 'Content-Type: application/json' \
  -d "$VIDEO_PAYLOAD" \
  | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('status:', d.get('status'))
for s in d.get('stages',[]):
    icon = '✓' if s['status']=='completed' else '✗'
    print(f'  {icon} {s[\"stage\"]:<25}{s.get(\"detail\",\"\")[:60]}')
urls = d.get('video_urls',{})
if urls:
    print('URLs:')
    for k,v in urls.items():
        print(f'  {k}: {v}')
if d.get('error'):
    print('ERROR:', d['error'])
"
```

---

## Full preset flow with character reference (matches manual_test.py exactly)

```bash
cd backend && python manual_test.py --base-url http://localhost:8000
```

---

## Check video output files on disk

```bash
ls -lh backend/outputs/projects/ 2>/dev/null || echo "No local outputs yet (GCS may be configured)"
find /tmp -name "voicevid_*.wav" 2>/dev/null | head -5
```
