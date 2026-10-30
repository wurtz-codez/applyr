# API contracts

Export the current FastAPI schema from the repository root:

```sh
cd apps/api
uv run python ../../scripts/export_openapi.py
cd ../..
pnpm contracts
```

Commit `openapi.json` and `src/api.d.ts` after generation. The web foundation currently
uses local profile types; replace them with the generated schema types when generated
contracts are available. Do not maintain two independent API contracts as features grow.
