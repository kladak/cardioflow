# CardioFlow frontend

Created in **Phase 0** (IMPLEMENTATION_PLAN.md). This directory currently holds only design tokens.

## Create the app

`create-next-app` refuses non-empty directories, so scaffold beside it and merge:

```bash
cd /path/to/cardioflow
npx create-next-app@latest frontend-tmp --ts --eslint --tailwind --app --src-dir --import-alias "@/*" --use-npm
cp -rn frontend-tmp/. frontend/ && rm -rf frontend-tmp
cd frontend
npm i @tanstack/react-query lucide-react
npm i -D openapi-typescript vitest @vitejs/plugin-react jsdom @testing-library/react @testing-library/jest-dom @testing-library/user-event
```

Add scripts: `"test": "vitest"`, `"typecheck": "tsc --noEmit"`.

## Tokens

`design-tokens.css` defines CSS variables. Import it first in `src/app/globals.css`. With Tailwind v4, expose them via
`@theme inline { --color-surface: var(--cf-surface); ... }`; with v3, map them in `tailwind.config.ts` `theme.extend.colors`.
Use token names in components (`bg-surface`, `text-ink-muted`, `border-rule`), never raw hex.

Fonts: `IBM_Plex_Sans` (400, 500, 600) and `IBM_Plex_Mono` (400, 500) from `next/font/google`, exposed as
`--cf-font-sans` / `--cf-font-mono`.

## Rules

- API types only from `src/lib/api-types.ts` (`make gen-api`).
- Server state only in TanStack Query; `tab` and `fact` in the URL; no global store.
- No component library. Hand-rolled primitives in `src/components/ui/`.
- See PRODUCT_SPEC.md §4–§8 for layout, states, copy, and component inventory.
