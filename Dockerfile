FROM nvidia/cuda:12.6.3-cudnn-runtime-ubuntu24.04

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive

# Install Python 3.12 + system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.12 python3.12-venv python3-pip \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/bin/python3.12 /usr/bin/python3 \
    && ln -sf /usr/bin/python3.12 /usr/bin/python

WORKDIR /app

# Install uv
RUN pip install --break-system-packages "uv==0.10.2"

# Copy manifest + source
COPY pyproject.toml uv.lock README.md ./
COPY src ./src

# Install dependencies
RUN uv export --frozen --no-hashes -o requirements.txt \
    && uv pip install --system --break-system-packages -r requirements.txt \
    && uv pip install --system --break-system-packages --no-deps .

EXPOSE 5000

CMD ["uvicorn", "whisper_bench.server:app", "--host", "0.0.0.0", "--port", "5000"]
