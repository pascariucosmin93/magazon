# syntax=docker/dockerfile:1
FROM alpine:3.20 AS builder

WORKDIR /html
COPY frontend/public /html

FROM nginx:1.27-alpine AS runtime

COPY --from=builder /html /usr/share/nginx/html
COPY frontend/nginx/default.conf /etc/nginx/conf.d/default.conf

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://localhost/ || exit 1
