#!/bin/bash
NAME=${1:-server1}
docker rm -f cc2-${NAME} || true