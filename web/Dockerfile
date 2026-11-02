FROM node:22-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173

# Vite dev server. VITE_API_URL is read from the container environment at startup.
CMD ["npm", "run", "dev"]
