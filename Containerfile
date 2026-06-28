# Build-tooling image: Raspberry Pi OS (trixie, 64-bit) + Debian build deps.
# Build it once, then reuse for fast iterative .deb builds.
FROM docker.io/vascoguita/raspios:trixie

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        debhelper \
        devscripts \
        dpkg-dev \
        fakeroot \
        python3 \
        python3-venv \
        python3-dev \
        libffi-dev \
        swig \
        liblgpio-dev \
        ca-certificates && \
    # Add any other -dev libraries your requirements.txt needs to compile here,
    # e.g. libbluetooth-dev
    rm -rf /var/lib/apt/lists/*

WORKDIR /build