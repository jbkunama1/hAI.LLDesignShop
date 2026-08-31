FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Ensure pip is up to date and install aiosqlite first (required for async sqlite)
RUN pip install --upgrade pip && pip install aiosqlite==0.20.0

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /data

CMD ["python", "bot.py"]
