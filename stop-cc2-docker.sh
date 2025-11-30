#!/bin/bash
NAME=${1:-server}
docker rm -f cc2-${NAME} || true