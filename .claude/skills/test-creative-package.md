Test the Creative Director interleaved endpoint and save all generated images to disk for inspection.

Uses `backend/test_creative_director.py` which tests all four modes and saves images to `/tmp/creative_director_test/`.

---

## Run all four modes

```bash
cd backend && python test_creative_director.py --base-url http://localhost:8000
```

## Run a single mode

```bash
# marketing (headline + hero image + copy + CTA visual)
cd backend && python test_creative_director.py --mode marketing

# storybook (narrative + illustrations)
cd backend && python test_creative_director.py --mode storybook

# educational (concept explanations + diagrams)
cd backend && python test_creative_director.py --mode educational

# social_content (caption + post image + hashtags)
cd backend && python test_creative_director.py --mode social_content
```

## Inspect output images (macOS)

```bash
open /tmp/creative_director_test/
```

## Quick one-liner — marketing package, custom brief

```bash
curl -s -X POST http://localhost:8000/api/v1/creative-director/generate \
  -H 'Content-Type: application/json' \
  -d '{"brief":"YOUR BRIEF HERE","mode":"marketing","art_style":"cinematic"}' \
  | python3 -c "
import sys, json, base64, pathlib
d = json.load(sys.stdin)
out = pathlib.Path('/tmp/cd_quick')
out.mkdir(exist_ok=True)
img_n = 0
for i, b in enumerate(d['blocks']):
    if b['type'] == 'text':
        print(f'[text] {b[\"content\"][:200]}')
    else:
        img_n += 1
        p = out / f'img_{img_n}.png'
        p.write_bytes(base64.b64decode(b['content']))
        print(f'[image] saved → {p}')
print(f'\ntotal: {d[\"total_text_blocks\"]} text, {d[\"total_images\"]} images')
"
```

## Validate response schema

```bash
curl -s -X POST http://localhost:8000/api/v1/creative-director/generate \
  -H 'Content-Type: application/json' \
  -d '{"brief":"Test brief for schema validation","mode":"social_content"}' \
  | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert 'package_id' in d, 'missing package_id'
assert 'blocks' in d, 'missing blocks'
assert 'total_images' in d, 'missing total_images'
assert 'total_text_blocks' in d, 'missing total_text_blocks'
assert all(b['type'] in ('text','image') for b in d['blocks']), 'invalid block type'
print('Schema OK ✓')
print(f'  package_id: {d[\"package_id\"]}')
print(f'  blocks: {len(d[\"blocks\"])} ({d[\"total_text_blocks\"]} text, {d[\"total_images\"]} images)')
"
```
