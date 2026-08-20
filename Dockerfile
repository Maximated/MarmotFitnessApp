FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /code

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

COPY . .
RUN uv sync --frozen
RUN chmod +x docker-entrypoint.sh

# Baked in at build time so the running app can report its own version even
# when deployed by pulling this image (no .git directory available then) --
# see app/version.py. Empty on a local `docker build` with no --build-arg;
# the app falls back to reading .git directly in that case.
ARG GIT_SHA=""
RUN echo "$GIT_SHA" > VERSION

RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --shell /bin/sh --create-home app \
    && chown -R app:app /code
USER app

EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
