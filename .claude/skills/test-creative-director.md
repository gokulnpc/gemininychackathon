Test the Creative Director interleaved endpoint with all four modes.

Runs four curl calls against the local backend and prints a summary of returned blocks (text count + image count per mode).

```bash
BASE=http://localhost:8000/api/v1/creative-director/generate

echo "=== MARKETING ===" && curl -s -X POST $BASE \
  -H 'Content-Type: application/json' \
  -d '{"brief":"AI productivity app for remote teams","mode":"marketing","art_style":"cinematic"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'text={d[\"total_text_blocks\"]} images={d[\"total_images\"]} blocks={len(d[\"blocks\"])}')"

echo "=== STORYBOOK ===" && curl -s -X POST $BASE \
  -H 'Content-Type: application/json' \
  -d '{"brief":"A child who discovers a magic library","mode":"storybook","art_style":"ghibli"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'text={d[\"total_text_blocks\"]} images={d[\"total_images\"]} blocks={len(d[\"blocks\"])}')"

echo "=== EDUCATIONAL ===" && curl -s -X POST $BASE \
  -H 'Content-Type: application/json' \
  -d '{"brief":"How neural networks learn","mode":"educational","art_style":"sketch"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'text={d[\"total_text_blocks\"]} images={d[\"total_images\"]} blocks={len(d[\"blocks\"])}')"

echo "=== SOCIAL ===" && curl -s -X POST $BASE \
  -H 'Content-Type: application/json' \
  -d '{"brief":"Morning routine for peak performance","mode":"social_content","art_style":"realism"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'text={d[\"total_text_blocks\"]} images={d[\"total_images\"]} blocks={len(d[\"blocks\"])}')"
```
