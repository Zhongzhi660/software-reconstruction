FROM debian:bookworm-slim
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl tar libfuse2 file python3 && \
    rm -rf /var/lib/apt/lists/*
RUN mkdir -p /opt/kicad && \
    curl -fL --retry 5 \
    -o /tmp/kicad.tar \
    https://downloads.kicad.org/kicad/linux/explore/stable/download/kicad-10.0.5-x86_64-lite.AppImage.tar && \
    tar -xf /tmp/kicad.tar -C /opt/kicad && \
    APPIMAGE="$(find /opt/kicad -maxdepth 2 -type f -name '*.AppImage' | head -n 1)" && \
    test -n "${APPIMAGE}" && chmod +x "${APPIMAGE}" && \
    ln -s "${APPIMAGE}" /usr/local/bin/kicad-appimage && \
    rm /tmp/kicad.tar

COPY app /app
RUN chmod +x /app/tools/feedback
WORKDIR /app/workspace
CMD ["sleep", "infinity"]
