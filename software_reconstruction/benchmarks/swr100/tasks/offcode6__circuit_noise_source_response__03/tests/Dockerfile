FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends ngspice && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir numpy
COPY . /tests
RUN chmod +x /tests/test.sh /tests/private/judge.py
WORKDIR /tests
ENV HOME=/tmp LC_ALL=C.UTF-8 PYTHONHASHSEED=0
CMD ["/tests/test.sh"]
