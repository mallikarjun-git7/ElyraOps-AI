FROM python:3.13-slim
WORKDIR /app
COPY elyraops/ ./elyraops/
COPY web/ ./web/
RUN useradd --create-home --uid 10001 app && mkdir -p /app/data && chown app:app /app/data
USER app
ENV PYTHONDONTWRITEBYTECODE=1 HOST=0.0.0.0 PORT=8080 ELYRA_DB_PATH=/app/data/elyraops.db
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health',timeout=2)" || exit 1
CMD ["python","-m","elyraops.server"]
