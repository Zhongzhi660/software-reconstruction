FROM microfluidica/openfoam:13
USER root
RUN apt-get update && apt-get install -y --no-install-recommends python3 && \
    rm -rf /var/lib/apt/lists/*

COPY app /app
RUN chmod +x /app/tools/feedback
WORKDIR /app/workspace
CMD ["sleep", "infinity"]
