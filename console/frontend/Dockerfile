# Ops-console frontend image. Build context = console/frontend.
#   docker build -t ops-console-frontend console/frontend
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# VITE_API_BASE_URL is baked at build time; override per environment.
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
