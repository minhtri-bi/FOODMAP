FROM ghcr.io/valhalla/valhalla@sha256:18cb42988e03c70dc4bc4ca095a259ec4db5e5df928be65956fc1c64c280b47a
RUN apt-get update \
    && apt-get install -y --no-install-recommends osmium-tool=1.16.0-1build1 \
    && rm -rf /var/lib/apt/lists/*
