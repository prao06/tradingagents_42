# TradingAgents web (Next.js, mobile-first)

A responsive web app for the TradingAgents dashboard — Home, Backtest, Journal,
and Decision views — that calls the FastAPI backend (`server/`). Deploys to
**Vercel**; the backend runs separately on an always-on host.

## Views
- **Home** — ticker command bar + latest-backtest and track-record tiles.
- **Backtest** — verdict, metric tiles, equity curve (inline SVG), folds, trades.
- **Journal** — track-record tiles + filterable decision log.
- **Decision** — decision card + the agent pipeline with investor-persona framing.

Mobile-first: fixed bottom tab nav, single-column cards that expand to grids on
wider screens, horizontally scrollable tables, and a web-app manifest so it can
be added to a phone home screen.

## Local dev
```bash
cd web
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev   # backend must be running
```

## Deploy to Vercel
1. In Vercel, import the repo and set **Root Directory = `web`** (Next.js is
   auto-detected).
2. Set env var **`NEXT_PUBLIC_API_URL`** to your deployed backend URL.
3. On the backend, set **`CORS_ORIGINS`** to your Vercel URL.

`NEXT_PUBLIC_API_URL` is read at build time, so redeploy after changing it.
