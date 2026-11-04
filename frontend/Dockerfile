# Build Stage: Compile React SPA with Vite
FROM node:20-alpine AS build

WORKDIR /app

# Install dependencies using locked versions
COPY package.json package-lock.json ./
RUN npm ci

# Copy frontend source files
COPY . .

# Set API URL prefix at build time so Vite bakes /api into client bundle
ARG VITE_API_URL=/api
ENV VITE_API_URL=${VITE_API_URL}

# Build static production assets into /app/dist
RUN npm run build

# Production Stage: Serve static assets via lightweight Nginx Alpine
FROM nginx:alpine

# Remove default Nginx welcome page
RUN rm -rf /usr/share/nginx/html/*

# Copy compiled static assets from build stage
COPY --from=build /app/dist /usr/share/nginx/html

# Copy custom baseline Nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Entrypoint script for automatic zero-code SSL detection and certificate reload
RUN printf '#!/bin/sh\n\
set -e\n\
\n\
configure_nginx() {\n\
    CERT=$(find /etc/letsencrypt/live -name fullchain.pem 2>/dev/null | head -n 1)\n\
    if [ -n "$CERT" ] && [ -f "$CERT" ]; then\n\
        KEY=$(dirname "$CERT")/privkey.pem\n\
        if [ -f "$KEY" ]; then\n\
            echo "[cpass-frontend] SSL certificate found ($CERT). Configuring HTTPS with HTTP-to-HTTPS redirect..."\n\
            cat <<EOF > /etc/nginx/conf.d/default.conf\n\
server {\n\
    listen 80;\n\
    listen [::]:80;\n\
    server_name _;\n\
\n\
    location /.well-known/acme-challenge/ {\n\
        root /var/www/certbot;\n\
        try_files \$uri =404;\n\
    }\n\
\n\
    location / {\n\
        return 301 https://\$host\$request_uri;\n\
    }\n\
}\n\
\n\
server {\n\
    listen 443 ssl http2;\n\
    listen [::]:443 ssl http2;\n\
    server_name _;\n\
\n\
    ssl_certificate $CERT;\n\
    ssl_certificate_key $KEY;\n\
    ssl_protocols TLSv1.2 TLSv1.3;\n\
    ssl_ciphers HIGH:!aNULL:!MD5;\n\
    ssl_prefer_server_ciphers on;\n\
    ssl_session_cache shared:SSL:10m;\n\
    ssl_session_timeout 1d;\n\
\n\
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;\n\
    add_header X-Frame-Options "SAMEORIGIN" always;\n\
    add_header X-Content-Type-Options "nosniff" always;\n\
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;\n\
\n\
    location /assets/ {\n\
        root /usr/share/nginx/html;\n\
        expires 1y;\n\
        add_header Cache-Control "public, immutable";\n\
        access_log off;\n\
    }\n\
\n\
    location /api/ {\n\
        rewrite ^/api/(.*) /\$1 break;\n\
        proxy_pass http://cpass-backend:8000;\n\
        proxy_http_version 1.1;\n\
        proxy_set_header Host \$host;\n\
        proxy_set_header X-Real-IP \$remote_addr;\n\
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;\n\
        proxy_set_header X-Forwarded-Proto https;\n\
        proxy_set_header X-Forwarded-Host \$host;\n\
        proxy_set_header X-Forwarded-Port \$server_port;\n\
        client_max_body_size 25M;\n\
        proxy_connect_timeout 60s;\n\
        proxy_read_timeout 180s;\n\
        proxy_send_timeout 180s;\n\
        proxy_buffering off;\n\
    }\n\
\n\
    location / {\n\
        root /usr/share/nginx/html;\n\
        index index.html index.htm;\n\
        try_files \$uri \$uri/ /index.html;\n\
    }\n\
\n\
    error_page 500 502 503 504 /50x.html;\n\
    location = /50x.html {\n\
        root /usr/share/nginx/html;\n\
    }\n\
}\n\
EOF\n\
            return 0\n\
        fi\n\
    fi\n\
    echo "[cpass-frontend] No SSL certificate found. Serving HTTP-only on port 80..."\n\
}\n\
\n\
if [ "$1" = "reload" ]; then\n\
    configure_nginx\n\
    nginx -s reload\n\
    exit 0\n\
fi\n\
\n\
configure_nginx\n\
exec "$@"\n' > /docker-entrypoint.sh && chmod +x /docker-entrypoint.sh

# Expose HTTP and HTTPS ports
EXPOSE 80 443

# Health check to ensure Nginx is actively serving the SPA root
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD wget -q -O /dev/null http://localhost/ || exit 1

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]
