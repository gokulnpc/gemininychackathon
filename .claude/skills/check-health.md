Check if the backend is running and all endpoints are reachable.

Run the following checks in order and report any failures:

```bash
BASE=http://localhost:8000

echo "=== 1. Health ===" && curl -sf $BASE/health | python3 -m json.tool

echo "=== 2. Voices Catalog ===" && curl -sf $BASE/api/v1/voices | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'{len(d)} voices available:', list(d.keys())[:5])"

echo "=== 3. Auth Status ===" && curl -sf $BASE/api/v1/auth/status | python3 -m json.tool

echo "=== 4. Projects List ===" && curl -sf "$BASE/api/v1/projects?limit=3" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'total projects: {d.get(\"total\",\"?\")}'); [print(f'  - {p[\"project_id\"][:8]}... {p[\"status\"]}') for p in d.get('projects',[])[:3]]" 2>/dev/null || echo "(no projects yet)"

echo "=== 5. OpenAPI Docs reachable ===" && curl -sf $BASE/openapi.json | python3 -c "import sys,json; d=json.load(sys.stdin); routes=[r for r in d.get('paths',{})]; print(f'{len(routes)} routes registered'); [print(f'  {r}') for r in sorted(routes)]"
```

If the backend is not running, start it first with the `run-backend` skill.
