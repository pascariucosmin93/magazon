FROM nginxinc/nginx-unprivileged:stable-alpine3.23 AS runtime

USER root
RUN apk upgrade --no-cache
USER 101

COPY frontend/public /usr/share/nginx/html
COPY frontend/nginx/default.conf /etc/nginx/conf.d/default.conf

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://localhost:8080/ || exit 1
