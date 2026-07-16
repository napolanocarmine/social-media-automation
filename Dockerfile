# Social media automation — React web + FastAPI + scheduler (+ Streamlit legacy opzionale)

FROM node:22-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim-bookworm AS api

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SOCIAL_AUTOMATION_ROOT=/app \
    TZ=Europe/Rome \
    APP_TIMEZONE=Europe/Rome \
    PIP_NO_CACHE_DIR=1 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

COPY pyproject.toml README.md ./
COPY src ./src
COPY .streamlit ./.streamlit
COPY docker ./docker

RUN pip install --upgrade pip \
    && pip install -e ".[api,ui]" \
    && chmod +x /app/docker/entrypoint.sh /app/docker/dispatch-loop.sh

COPY config/categories.example.yaml config/categories.example.yaml
COPY config/canva.example.yaml config/canva.example.yaml
COPY config/schedule.example.yaml config/schedule.example.yaml
COPY config/vision_brand.example.yaml config/vision_brand.example.yaml

EXPOSE 8000 8501

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["api"]

FROM nginx:1.27-alpine AS web

COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=frontend-build /app/frontend/dist /usr/share/nginx/html

EXPOSE 80
