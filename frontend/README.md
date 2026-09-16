# CardioFlow frontend

The frontend is a Next.js application for reviewing synthetic encounter transcripts and structured findings.

## Commands

Run these from this directory after `npm install`:

```bash
npm run dev
npm test
npm run typecheck
npm run build
npm run start
```

The browser calls `/api/*` on the frontend origin. `next.config.ts` proxies those requests to `CARDIOFLOW_API_ORIGIN`, which defaults to `http://127.0.0.1:8010`.

API types in `src/lib/api-types.ts` are generated from the FastAPI OpenAPI document. Run `make gen-api` from the repository root after changing backend response models.

The interface imports the shared design tokens from `design-tokens.css`. It does not send custom transcript checker input to the backend.
