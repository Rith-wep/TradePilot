#!/bin/sh
set -eu
mkdir -p /tls
openssl req -x509 -newkey rsa:2048 -nodes -days 1 \
  -subj '/CN=TradePilot smoke CA' -keyout /tls/ca.key -out /tls/ca.crt
openssl req -newkey rsa:2048 -nodes -subj '/CN=oidc' \
  -keyout /tls/server.key -out /tls/server.csr
printf '%s\n' 'subjectAltName=DNS:oidc,IP:127.0.0.1' 'extendedKeyUsage=serverAuth' >/tls/server.ext
openssl x509 -req -days 1 -in /tls/server.csr -CA /tls/ca.crt -CAkey /tls/ca.key \
  -CAcreateserial -extfile /tls/server.ext -out /tls/server.crt
exec node /app/server.mjs
