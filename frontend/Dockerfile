FROM node:20-alpine AS build

WORKDIR /app

RUN npm install -g npm@11

COPY package*.json ./
RUN npm ci

COPY angular.json tsconfig*.json ./
COPY src ./src
COPY public ./public

RUN npm run build

FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist/driftgate/browser /usr/share/nginx/html

EXPOSE 80
