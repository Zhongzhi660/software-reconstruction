FROM python:3.11-slim
RUN python3 -m pip install --no-cache-dir --upgrade pip setuptools wheel
RUN apt-get update && apt-get install -y --no-install-recommends libexpat1 && rm -rf /var/lib/apt/lists/*
RUN python3 -m pip install --no-cache-dir numpy rasterio pysheds
COPY app /app
RUN chmod +x /app/tools/feedback
WORKDIR /app/workspace
ENV HOME=/tmp LC_ALL=C.UTF-8 PYTHONHASHSEED=0
CMD ["sleep", "infinity"]
