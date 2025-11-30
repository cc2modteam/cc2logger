#!/bin/bash
CC2_INSTALL=${1:-${HOME}/cc2-server-install}
mkdir -p ${CC2_INSTALL}

set -e
rm -rf steamcmd-wine-xvfb-docker carrier-command-docker
git clone https://github.com/inorton/steamcmd-wine-xvfb-docker.git
git clone https://github.com/inorton/carrier-command-docker.git

git -C carrier-command-docker checkout -f bredlab

(
  cd steamcmd-wine-xvfb-docker
  docker build -t bredlab/wine-xvfb:stable .
)

(
  cd carrier-command-docker
  docker volume create \
    -d local \
    -o type=none \
    -o o=bind \
    -o device=${CC2_INSTALL} carrier-command
  make STEAM_USERNAME=iannorton
)