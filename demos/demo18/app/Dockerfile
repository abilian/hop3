# Demo 18: Docker Node.js/Express application
FROM node:20-alpine

WORKDIR /app

# Install dependencies first (better caching)
COPY package*.json ./
RUN npm install --production

# Copy application code
COPY . .

# Expose port
EXPOSE 8080

# Run the application
CMD ["npm", "start"]
