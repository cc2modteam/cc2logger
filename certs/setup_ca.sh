#!/bin/bash
set -ex
openssl genrsa -out ca.key 2048
openssl req -x509 -new -nodes -key ca.key -sha256 -days 3650 -out ./ca.crt

bash issue_client_cert.sh
bash issue_server_cert.sh
