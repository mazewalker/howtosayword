FROM python:3.11-slim
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir "fastapi>=0.110" "uvicorn[standard]>=0.29" "email-validator>=2.0"
WORKDIR /app
COPY api.py /app/api.py
COPY sub_store.py /app/sub_store.py
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request,sys; r=urllib.request.urlopen('http://127.0.0.1:8000/healthz',timeout=3); sys.exit(0 if r.status==200 else 1)"
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
