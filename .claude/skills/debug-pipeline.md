Debug a failed or stuck pipeline run. Run the relevant checks based on which stage failed.

---

## 1. Check backend logs (if running in foreground terminal — otherwise check uvicorn output)

```bash
curl -s http://localhost:8000/health
```

## 2. Diagnose by stage failure

### TTS failed (Stage 1)
```bash
# Test TTS directly
cd backend && python3 -c "
import asyncio
from services.gemini_tts import generate_voiceover
path = asyncio.run(generate_voiceover('Hello world, this is a test.', 'Aoede'))
print('WAV saved to:', path)
import os; print('size:', os.path.getsize(path), 'bytes')
"
```

### Image generation failed (Stage 2)
```bash
# Test image generation for one scene
cd backend && python3 -c "
import asyncio
from services.gemini_image import generate_scene_image
path = asyncio.run(generate_scene_image(
    prompt='A lone explorer standing on a misty mountain peak at dawn, dramatic lighting, sense of achievement',
    scene_index=0,
    art_style='cinematic',
))
print('Image saved to:', path)
"
```

### FFmpeg failed (Stage 3/5)
```bash
# Check FFmpeg is installed and working
which ffmpeg && ffmpeg -version | head -3

# Test zoompan animation with a dummy image
ffmpeg -f lavfi -i color=c=blue:size=576x1024:duration=1 \
  -vf "zoompan=z='min(zoom+0.004,1.5)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=576x1024:d=125,fps=25" \
  -c:v libx264 -pix_fmt yuv420p -t 5 /tmp/ffmpeg_test.mp4 -y 2>&1 | tail -5
echo "Exit: $?"
```

### GCS upload failed (Stage 6) — check if fallback to local worked
```bash
ls -lhR backend/outputs/projects/ 2>/dev/null | head -30
echo "---"
# Check GCS config
cd backend && python3 -c "
from config import get_settings
s = get_settings()
print('gcs_bucket:', s.gcs_bucket)
print('google_cloud_project:', s.google_cloud_project or '(not set — local fallback active)')
"
```

### Creative Director interleaved failed
```bash
# Verify model and modalities work
cd backend && python3 -c "
from config import get_settings
from google import genai
from google.genai import types
s = get_settings()
client = genai.Client(api_key=s.gemini_api_key or None)
resp = client.models.generate_content(
    model='gemini-2.0-flash-preview-image-generation',
    contents='Write one sentence and generate one small image of a blue circle.',
    config=types.GenerateContentConfig(response_modalities=['TEXT', 'IMAGE']),
)
for p in resp.candidates[0].content.parts:
    if getattr(p,'text',None):
        print('TEXT:', p.text[:80])
    elif getattr(p,'inline_data',None):
        print('IMAGE: mime=', p.inline_data.mime_type, 'bytes=', len(p.inline_data.data or b''))
"
```

## 3. Check recent project outputs

```bash
# Find the latest project directory
ls -lt backend/outputs/projects/ 2>/dev/null | head -5

# Inspect a specific project (replace PROJECT_ID)
PROJECT_ID="replace-me"
ls -lh backend/outputs/projects/$PROJECT_ID/ 2>/dev/null
```

## 4. Tail backend server logs

If uvicorn is running in another terminal, the logs appear there.
To capture them to a file during a test run:
```bash
cd backend && python -m uvicorn main:app --reload --port 8000 2>&1 | tee /tmp/backend.log
# Then in another terminal:
tail -f /tmp/backend.log | grep -E "(ERROR|WARNING|INFO.*stage|INFO.*Creative)"
```
