FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY . .
RUN uv pip install --system -e ".[dev]"

CMD ["bugsi", "run", "--mock"]
