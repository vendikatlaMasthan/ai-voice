# ==============================================================================
# VoiceShield AI - Production Multi-Runtime Container (Node.js 20 + Python 3.11)
# ==============================================================================

FROM python:3.11-slim-bookworm

# 1. Install system utilities and audio processing libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    gnupg \
    build-essential \
    libsndfile1 \
    libsndfile1-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 2. Install Node.js 20 LTS
RUN mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg && \
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list && \
    apt-get update && apt-get install -y --no-install-recommends nodejs && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 3. Install Python ML dependencies with pip cache optimization
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 4. Install Node.js dependencies
COPY package*.json ./
RUN npm ci || npm install

# 5. Copy project source code (respecting .dockerignore)
COPY . .

# 6. Build the Vite React frontend and esbuild Node server
RUN npm run build

# 7. Production Runtime Configuration
ENV NODE_ENV=production \
    PORT=3000 \
    PYTHONUNBUFFERED=1

EXPOSE 3000

# 8. Start the unified Express server with persistent inference daemon
CMD ["node", "dist/server.cjs"]
