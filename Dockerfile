FROM python:3.10.18-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock /app/
RUN uv sync --frozen --no-dev

COPY . /app

RUN sed -i 's/\r$//' /app/start.sh \
    && chmod +x /app/start.sh

EXPOSE 8000

CMD ["/app/start.sh"]
