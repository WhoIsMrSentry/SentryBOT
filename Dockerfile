FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Runtime libs for OpenCV/audio related optional modules,
# plus build tools for packages that may need compilation.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        ffmpeg \
        libglib2.0-0 \
        libgl1 \
        libgomp1 \
        libsm6 \
        libsndfile1 \
        libxext6 \
        libxrender1 \
        portaudio19-dev \
    && rm -rf /var/lib/apt/lists/*

COPY . /app

# Install all module-scoped requirements in the repository.
RUN python install_all_requirements.py --fail-fast

EXPOSE 8080

# Docker defaults can be overridden at runtime.
ENV GATEWAY_CONFIG=/app/modules/gateway/config/config.docker.yml

HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8080/healthz || exit 1

CMD ["python", "run_robot.py"]
