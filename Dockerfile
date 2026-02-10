FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY pyproject.toml README.md ./
COPY src ./src
COPY tests ./tests
COPY data ./data
COPY configs ./configs
COPY scripts ./scripts
COPY examples ./examples
COPY .pre-commit-config.yaml ./
COPY Makefile ./

RUN pip install --upgrade pip && \ 
    pip install .[dev]

CMD ["bash"]
