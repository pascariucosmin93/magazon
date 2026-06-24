FROM public.ecr.aws/docker/library/nginx:stable-alpine3.23 AS runtime

# Rebuild 2026-06-24: pick up Alpine patches for CVE-2026-22184 (zlib),
# CVE musl/libxml2/libpng/openssl/nghttp2/libexpat series (May 2026 batch)
RUN apk upgrade --no-cache

COPY frontend/public /usr/share/nginx/html
COPY frontend/nginx/default.conf /etc/nginx/conf.d/default.conf

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://localhost/ || exit 1
