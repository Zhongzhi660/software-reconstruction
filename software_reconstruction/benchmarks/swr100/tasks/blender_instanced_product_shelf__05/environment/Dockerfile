FROM debian:bookworm-slim
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl xz-utils openscad chromium xvfb git python3 build-essential \
    libx11-6 libxext6 libxrender1 libxi6 libxfixes3 libxkbcommon0 \
    libsm6 libice6 libgl1 libegl1 libfontconfig1 libdbus-1-3 \
    libwayland-client0 libwayland-egl1 && \
    rm -rf /var/lib/apt/lists/*
RUN curl -fL --retry 5 \
    -o /tmp/blender.tar.xz \
    https://mirrors.ocf.berkeley.edu/blender/release/Blender4.2/blender-4.2.8-linux-x64.tar.xz && \
    mkdir -p /opt/blender && \
    tar -xJf /tmp/blender.tar.xz --strip-components=1 -C /opt/blender && \
    ln -s /opt/blender/blender /usr/local/bin/blender && \
    rm /tmp/blender.tar.xz
RUN curl -fL --retry 5 \
    -o /tmp/node.tar.xz \
    https://nodejs.org/dist/v22.18.0/node-v22.18.0-linux-x64.tar.xz && \
    mkdir -p /opt/node && \
    tar -xJf /tmp/node.tar.xz --strip-components=1 -C /opt/node && \
    ln -s /opt/node/bin/node /usr/local/bin/node && \
    ln -s /opt/node/bin/npm /usr/local/bin/npm && \
    ln -s /opt/node/bin/npx /usr/local/bin/npx && \
    /opt/node/bin/npm install -g pnpm bun && \
    ln -s /opt/node/bin/pnpm /usr/local/bin/pnpm && \
    ln -s /opt/node/bin/bun /usr/local/bin/bun && \
    rm /tmp/node.tar.xz
ENV LIBGL_ALWAYS_SOFTWARE=1
ENV CYCLES_DEVICE=CPU

COPY app /app
RUN chmod +x /app/tools/feedback
WORKDIR /app/workspace
CMD ["sleep", "infinity"]
