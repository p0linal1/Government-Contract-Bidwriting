# The Cadocary app on Cloud Run: the prototype's build, served by the small server in server/.
# The key comes from Secret Manager at run time (see server/main.py), never from this image.

FROM node:22-slim AS app
WORKDIR /build/prototype
COPY prototype/package.json prototype/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY prototype/ ./
RUN npm run build

FROM python:3.13-slim
WORKDIR /srv
COPY server/requirements.txt server/
RUN pip install --no-cache-dir -r server/requirements.txt
COPY agent/ids.json agent/
COPY server/ server/
COPY --from=app /build/prototype/dist prototype/dist
CMD ["sh", "-c", "exec uvicorn main:app --app-dir server --host 0.0.0.0 --port ${PORT:-8080}"]
