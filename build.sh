#!/usr/bin/env bash
#
# Build the pitilt .deb inside a Raspberry Pi OS (trixie) container with podman.
#
# Usage:
#   ./build.sh                 # 64-bit (arm64), installs build deps each run
#   ARCH=armhf ./build.sh      # 32-bit (arm/v7)
#   PREBUILT=1 ./build.sh      # use the pre-baked image from the Containerfile
#
# On an x86_64 host you need qemu binfmt registered so the arm container can
# run. With podman the easiest way is:
#   podman run --rm --privileged docker.io/multiarch/qemu-user-static --reset -p yes
# (On a Raspberry Pi / arm64 host this is not needed.)
#
set -euo pipefail

ARCH="${ARCH:-arm64}"                 # arm64 | armhf
PREBUILT="${PREBUILT:-0}"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUTDIR="${PROJECT_DIR}/dist"

case "$ARCH" in
    arm64) PLATFORM="linux/arm64";  BASE_TAG="trixie" ;;
    armhf) PLATFORM="linux/arm/v7"; BASE_TAG="armhf-trixie" ;;
    *) echo "Unknown ARCH '$ARCH' (use arm64 or armhf)" >&2; exit 1 ;;
esac

mkdir -p "$OUTDIR"

if [ "$PREBUILT" = "1" ]; then
    IMAGE="pitilt-build:${ARCH}"
    echo ">> Building tooling image ${IMAGE} ..."
    podman build --platform "$PLATFORM" -t "$IMAGE" -f "${PROJECT_DIR}/Containerfile" "$PROJECT_DIR"
    INSTALL_DEPS=""
else
    IMAGE="docker.io/vascoguita/raspios:${BASE_TAG}"
    INSTALL_DEPS="apt-get update && apt-get install -y --no-install-recommends \
        build-essential debhelper devscripts dpkg-dev fakeroot \
        python3 python3-venv python3-dev libffi-dev ca-certificates &&"
fi

echo ">> Building pitilt .deb for ${ARCH} using ${IMAGE} ..."
podman run --rm \
    --platform "$PLATFORM" \
    -v "${PROJECT_DIR}":/build:Z \
    -w /build \
    "$IMAGE" \
    bash -euo pipefail -c "
        export DEBIAN_FRONTEND=noninteractive
        ${INSTALL_DEPS}
        # Binary-only, unsigned build. Artifacts land in the parent dir (/).
        dpkg-buildpackage -b -us -uc
        mkdir -p /build/dist
        cp /*.deb /build/dist/ 2>/dev/null || true
        cp /*.buildinfo /*.changes /build/dist/ 2>/dev/null || true
    "

echo
echo ">> Built packages in ${OUTDIR}:"
ls -1 "${OUTDIR}"/*.deb 2>/dev/null || { echo "  (no .deb produced - check the log above)"; exit 1; }
