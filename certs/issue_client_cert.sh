#!/bin/bash
#
# Issue a the control server client keypair
#

set -ex

openssl genrsa -out client.key 2048
openssl req -new -key client.key -out client.csr -config client.conf
openssl x509 -req -in client.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out client.crt -days 365 -sha256 -extensions req_ext -extfile client.conf