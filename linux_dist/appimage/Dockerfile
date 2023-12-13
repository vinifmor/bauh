FROM ubuntu:20.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update -y && \
    apt-get upgrade -y && \
    apt-get install --no-install-recommends python3-pip python3-setuptools python3-wheel wget fuse binutils coreutils desktop-file-utils fakeroot patchelf squashfs-tools strace zsync libgdk-pixbuf2.0-dev gtk-update-icon-cache file -y && \
    mkdir /build && cd /build && \
    wget https://github.com/AppImageCrafters/appimage-builder/releases/download/v0.9.2/appimage-builder-0.9.2-35e3eab-x86_64.AppImage -O appimage-builder && \
    wget https://github.com/AppImage/AppImageKit/releases/download/13/appimagetool-x86_64.AppImage -O appimage-tool && \
    chmod +x appimage-tool && \
    chmod +x appimage-builder && \
    mv /build/appimage-builder /usr/local/bin/appimage-builder && \
    mv /build/appimage-tool /usr/local/bin/appimage-tool

WORKDIR /build

CMD [ "appimage-builder", "--skip-tests"]
