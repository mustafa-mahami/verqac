FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && playwright install --with-deps chromium \
 && rm -rf /var/lib/apt/lists/*

COPY . .
RUN useradd --system --uid 1001 verqac && mkdir -p /data/files && chown -R verqac /app /data/files
USER verqac

EXPOSE 8000
# worker processes (uvicorn reads WEB_CONCURRENCY): a page asks for several things at once, each one in its own worker
ENV WEB_CONCURRENCY=4
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
