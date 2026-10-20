FROM node:22-alpine AS ui
WORKDIR /build/frontend
ARG VITE_BUILD_SHA=local
ENV VITE_BUILD_SHA=${VITE_BUILD_SHA}
COPY frontend/package.json frontend/package-lock.json frontend/index.html frontend/tsconfig.json ./
COPY frontend/src ./src
RUN npm ci && npm run build

FROM python:3.12-slim AS base
WORKDIR /app
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend ./backend
COPY seed ./seed
ENV PYTHONPATH=/app/backend

# Test image: `docker build --target test .` then `docker run <image> pytest`.
FROM base AS test
RUN pip install --no-cache-dir pytest pytest-asyncio
COPY tests ./tests
COPY pytest.ini ./pytest.ini
# Required by tests/test_phase1d_opa.py and the UI contract tests.
COPY .launch/opa/authz.rego ./.launch/opa/authz.rego
COPY frontend/src ./frontend/src
COPY --from=ui /build/frontend/dist ./frontend/dist

# Runtime image (default target): no tests, no dev files, non-root.
FROM base AS runtime
COPY --from=ui /build/frontend/dist ./frontend/dist
RUN useradd --system --uid 10001 --no-create-home app
USER app
ENV PORT=8080
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT','8080'),timeout=4)"
# The app keeps rate limits and caches in memory, so it must run as a single worker.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1"]
