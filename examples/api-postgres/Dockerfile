FROM python:3.13-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml .
COPY src/ src/

# Install pulice from PyPI (in production) or copy from workspace
RUN uv pip install --system -e ".[api]" || pip install -e "."

ENV PULICE_STATE_DIR=/data/pulice

EXPOSE 8000
