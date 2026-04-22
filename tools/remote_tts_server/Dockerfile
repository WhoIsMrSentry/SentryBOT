FROM python:3.10-slim

# Install system dependencies required for TTS and Piper
RUN apt-get update && apt-get install -y \
    build-essential \
    libsndfile1 \
    ffmpeg \
    espeak-ng \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Expose server port
EXPOSE 5000

# Set environment variables
ENV SENTRYBOT_HOST=0.0.0.0
ENV SENTRYBOT_PORT=5000
ENV SENTRYBOT_OLLAMA_TAGS_ENDPOINT=https://localhost:5000/api/tags
# Volume paths for persistence
ENV SENTRYBOT_TTS_ROOT=/app/runtime
ENV SENTRYBOT_PIPER_ROOT=/app/runtime/piper_models
ENV SENTRYBOT_XTTS_ROOT=/app/runtime/xtts

# Persistence volume for TTS catalogs and voices
VOLUME ["/app/runtime"]

# Run the FastAPI app via uvicorn
CMD ["python", "app.py"]
