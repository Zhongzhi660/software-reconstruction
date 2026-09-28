FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends libexpat1 && rm -rf /var/lib/apt/lists/*
COPY . /tests
RUN python3 -m pip install --no-cache-dir --upgrade pip setuptools wheel numpy
RUN python3 -m pip install --no-cache-dir numpy rasterio pysheds
RUN chmod +x /tests/test.sh /tests/private/judge.py
WORKDIR /tests
ENV HOME=/tmp LC_ALL=C.UTF-8 PYTHONHASHSEED=0
CMD ["/tests/test.sh"]
