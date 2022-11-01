#!/bin/bash
docker build -t bauh-appimage --build-arg bauh_commit=$BAUH_COMMIT .
docker run --cap-add=SYS_ADMIN --device /dev/fuse --mount type=bind,source="$(pwd)",target=/build bauh-appimage
