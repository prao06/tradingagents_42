# TradingAgents FastAPI backend — deploy to Render / Railway / Fly / any VM.
# Python 3.13: tradingagents pulls tiktoken, which has no wheel for 3.14+.
FROM python:3.13-slim

WORKDIR /app
RUN pip install --no-cache-dir uv

# Install dependencies against the project (server extra = fastapi + uvicorn).
COPY pyproject.toml uv.lock README.md ./
COPY tradingagents ./tradingagents
COPY cli ./cli
RUN uv pip install --system --no-cache ".[server]"

# App code (server/ and dashboard/ are imported from the working dir, not the
# installed package).
COPY server ./server
COPY dashboard ./dashboard

EXPOSE 8000
# Hosts inject $PORT; default to 8000 locally.
CMD ["sh", "-c", "uvicorn server.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
