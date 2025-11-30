#!/bin/bash
set -e
NAME=${1:-server}
IMAGE=bredlab/cc2-server:stable

docker rm -f cc2-${NAME} || true
docker run \
  -p 25565:25565/udp -p 25566:25566/udp -p 25567:25567/udp -p 25568:25568/udp \
  --rm --name cc2-${NAME} -v carriercommand:/carriercommand -id ${IMAGE}
