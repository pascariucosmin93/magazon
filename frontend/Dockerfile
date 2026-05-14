# syntax=docker/dockerfile:1
FROM nginx:stable-alpine3.23 AS runtime

COPY frontend/public /usr/share/nginx/html
COPY frontend/nginx/default.conf /etc/nginx/conf.d/default.conf

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://localhost/ || exit 1
