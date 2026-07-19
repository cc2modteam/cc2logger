#!/bin/bash
set -e
rm -rf dist
python3 -m build -w
docker build -t cc2teams -f Dockerfile.teams .