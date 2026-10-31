FROM node:22-bookworm-slim
WORKDIR /app
COPY server/package.json server/package-lock.json ./
RUN npm ci --omit=dev && apt-get update && apt-get install -y --no-install-recommends openssl \
 && rm -rf /var/lib/apt/lists/*
COPY server/docker/oidc/server.mjs ./server.mjs
COPY --chmod=0555 server/docker/oidc/start.sh /usr/local/bin/start-smoke-oidc
EXPOSE 8443
ENTRYPOINT ["start-smoke-oidc"]
