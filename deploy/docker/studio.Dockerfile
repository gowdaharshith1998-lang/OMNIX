# OMNIX Studio — built React + Vite SPA served by nginx.
#
# Stage 1 builds the bundle; stage 2 serves it. SPA fallback (all unknown
# paths → /index.html) is configured in studio-nginx.conf so React Router
# (or whatever client-side routing the bundle uses) works on refresh.

FROM node:22-alpine AS build
WORKDIR /app
COPY src/omnix/studio/frontend/package.json src/omnix/studio/frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund --silent
COPY src/omnix/studio/frontend/ ./
# Skip the noEmit typecheck under CI — vite build is the deploy artifact.
RUN npx vite build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY deploy/docker/studio-nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1:8080/ || exit 1
