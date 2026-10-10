FROM node:22-alpine AS ui
WORKDIR /build/frontend
ARG VITE_BUILD_SHA=local
ENV VITE_BUILD_SHA=${VITE_BUILD_SHA}
COPY frontend/package.json frontend/package-lock.json frontend/index.html ./
COPY frontend/src ./src
RUN npm ci && npm run build
FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend ./backend
COPY seed ./seed

COPY tests ./tests
COPY pytest.ini ./pytest.ini

# Required by tests/test_phase1d_opa.py when the suite runs inside the image.
COPY frontend/src ./src
COPY frontend/src/App.tsx ./frontend/src/App.tsx
COPY .launch/opa/authz.rego ./.launch/opa/authz.rego

COPY --from=ui /build/frontend/dist ./frontend/dist

ENV PORT=8080 PYTHONPATH=/app/backend
EXPOSE 8080
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
