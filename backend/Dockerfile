FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

ENV PYTHONUNBUFFERED=1

RUN groupadd --system --gid 999 nonroot \
  && useradd --system --gid 999 --uid 999 --create-home nonroot

WORKDIR /app/

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy

# Omit development dependencies
ENV UV_NO_DEV=1

# Ensure installed tools can be executed out of the box
ENV UV_TOOL_BIN_DIR=/usr/local/bin

# Install the project's dependencies using the lockfile and settings
RUN --mount=type=cache,target=/root/.cache/uv \
  --mount=type=bind,source=uv.lock,target=uv.lock \
  --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
  uv sync --frozen --no-install-workspace --package app

COPY ./backend/httpie /app/backend/httpie

COPY ./backend/pyproject.toml ./backend/alembic.ini /app/backend/

COPY ./backend/app /app/backend/app 

RUN --mount=type=cache,target=/root/.cache/uv \
  --mount=type=bind,source=uv.lock,target=uv.lock \
  --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
  uv sync --frozen --package app

ENV UV_PROJECT_ENVIRONMENT=/app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Reset the entrypoint, don't invoke `uv`
ENTRYPOINT []

# Ensure the non-root user can write to the app directories
RUN chown -R nonroot:nonroot /app

# Use the non-root user to run our application
USER nonroot

WORKDIR /app/backend/

# Development
CMD ["uv", "run", "fastapi", "dev", "--host", "0.0.0.0", "app/main.py"]
# Prodcution
# CMD [ "fastapi", "run", "--workers", "4", "app/main.py" ]

