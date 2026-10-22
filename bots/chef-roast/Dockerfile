FROM node:22-slim
WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev
COPY src ./src
ENV DB_PATH=/data/database.db
CMD ["node", "src/bot.js"]
