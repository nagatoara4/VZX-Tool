FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN addgroup --system app && adduser --system --ingroup app app && mkdir -p /data && chown -R app:app /app /data
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py platform_api.py agent_worker.py agent_engine.py integration_registry.py provider_adapters.py amazon_catalog.py dashboard.html ./
RUN chown -R app:app /app
USER app
ENV COMMERCE_DB_PATH=/data/commerce.db
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).read()"
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
