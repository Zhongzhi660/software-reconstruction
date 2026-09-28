FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl xz-utils git build-essential python3 openssl && \
    rm -rf /var/lib/apt/lists/*
RUN curl -fL --retry 5 \
    -o /tmp/node.tar.xz \
    https://nodejs.org/dist/v22.18.0/node-v22.18.0-linux-x64.tar.xz && \
    mkdir -p /opt/node && \
    tar -xJf /tmp/node.tar.xz --strip-components=1 -C /opt/node && \
    ln -s /opt/node/bin/node /usr/local/bin/node && \
    ln -s /opt/node/bin/npm /usr/local/bin/npm && \
    ln -s /opt/node/bin/npx /usr/local/bin/npx && \
    /opt/node/bin/npm install -g tree-sitter-cli && \
    ln -s /opt/node/bin/tree-sitter /usr/local/bin/tree-sitter && \
    rm /tmp/node.tar.xz

COPY app /app
RUN chmod +x /app/tools/feedback
WORKDIR /app/workspace
CMD ["sleep", "infinity"]
