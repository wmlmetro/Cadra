# syntax=docker/dockerfile:1.7
# ──────────────────────────────────────────────────────────────────────
# Cadra modern frontend — production image.
#
# Layout in the container:
#   /usr/share/nginx/html/index.html          ← SPA shell
#   /usr/share/nginx/html/assets/*            ← hashed JS/CSS bundles
#   /usr/share/nginx/html/favicon.svg, ...    ← public/ static files
#
# nginx serves these behind a sub-path (/app/) so the same staging
# ingress can keep routing /api/* + / to Odoo and just slot /app/* in.
#
# Build context: this directory (Frontend/artifacts/nrs-asset-register).
# ──────────────────────────────────────────────────────────────────────

# ─── Stage 1: build ──────────────────────────────────────────────────
FROM node:22-alpine AS build

WORKDIR /app

# Install deps separately so package.json changes alone bust the cache.
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . .

# Tell vite to emit the bundle assuming it lives at /app/* on the origin.
ENV BASE_PATH=/app/
ENV NODE_ENV=production
RUN npm run build

# ─── Stage 2: serve ──────────────────────────────────────────────────
FROM nginx:1.27-alpine AS serve

# Replace the stock nginx config with our SPA-aware one.
COPY --from=build /app/nginx.conf /etc/nginx/nginx.conf
COPY --from=build /app/dist/public /usr/share/nginx/html

# nginx in this image listens on 8080 (see nginx.conf) so we can run as
# a non-root user without binding to a privileged port.
EXPOSE 8080

# nginx:alpine ships with a pre-baked "nginx" user (UID 101) we can drop to.
# It needs write access to its temp/pid dirs.
# K8s `runAsNonRoot: true` can only statically verify a numeric USER value
# (a username could be "root" with a non-root UID, so the kubelet refuses
# to start the pod when USER is non-numeric). Use the UID directly.
RUN chown -R nginx:nginx /var/cache/nginx /var/run /var/log/nginx \
 && touch /run/nginx.pid && chown nginx:nginx /run/nginx.pid
USER 101

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -qO- http://127.0.0.1:8080/healthz || exit 1

CMD ["nginx", "-g", "daemon off;"]
