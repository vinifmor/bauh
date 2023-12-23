#!/bin/bash
set -Ceufox pipefail

docker build -t bauh-appimage .
docker run -e BAUH_VERSION=$BAUH_VERSION -v ./AppImageBuilder.yml:/build/AppImageBuilder.yml --rm --cap-add=SYS_ADMIN --device /dev/fuse --mount type=bind,source="$(pwd)",target=/build bauh-appimage
# volume required to run tests: -v /var/run/docker.sock:/var/run/docker.sock
