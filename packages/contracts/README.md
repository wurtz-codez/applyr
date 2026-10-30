# API contracts

`openapi.json` is generated from FastAPI; `src/api.d.ts` is generated from that schema.
The web client imports schema types through `apps/web/src/lib/types.ts`.

From the repository root, regenerate after changing API schemas:

```sh
cd apps/api
uv run python ../../scripts/export_openapi.py
cd ../..
pnpm contracts
```

Commit both generated files. Keep generation deterministic and do not hand-edit them.
