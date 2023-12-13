#!/bin/bash
set -Ceufox pipefail

docker build -t bauh-appimage . && \
docker run -e BAUH_VERSION=$BAUH_VERSION --cap-add=SYS_ADMIN --device /dev/fuse --mount type=bind,source="$(pwd)",target=/build bauh-appimage
