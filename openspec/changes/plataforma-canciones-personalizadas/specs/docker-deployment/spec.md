# Docker Deployment Specification

## Purpose

Provide a containerized deployment for CancionesPersonalizadas via Dockerfile and docker-compose, enabling consistent local development and production-ready Railway deployment with proper environment configuration, volume persistence, and health checking.

## Requirements

### RQ-DKR-01: Dockerfile

The system MUST provide a Dockerfile based on `python:3.11-slim` that installs dependencies from `pyproject.toml`, copies application code, exposes port 8000, and runs Uvicorn.

#### Scenario: Build succeeds

- GIVEN the Dockerfile and `pyproject.toml` in the project root
- WHEN `docker build -t canciones-personalizadas .` is executed
- THEN the build MUST exit 0
- AND the image MUST contain the application code at `/app/`
- AND port 8000 MUST be exposed

#### Scenario: Container starts and serves health check

- GIVEN a built image
- WHEN `docker run -p 8000:8000 canciones-personalizadas` is executed
- THEN the container MUST start Uvicorn on 0.0.0.0:8000
- AND `curl localhost:8000/api/auth/health` MUST return 200

### RQ-DKR-02: Docker Compose

The system MUST provide `docker-compose.yml` that defines the `api` service with environment variables, volume mounts for `output/` and `jobs.db`, and a health check configuration.

#### Scenario: Compose up starts service

- GIVEN `docker-compose.yml` in the project root
- WHEN `docker compose up -d` is executed
- THEN the api container MUST start
- AND the container health status MUST become `healthy` within 30s

#### Scenario: Output persistence across restarts

- GIVEN generated audio files in the container
- WHEN the container is stopped and restarted
- THEN the audio files MUST still be present in the mounted volume

### RQ-DKR-03: Environment Configuration

The system MUST provide `.env.docker` with sensible defaults for development. Docker Compose MUST load `env_file: .env.docker`.

#### Scenario: Environment variables loaded

- GIVEN `.env.docker` with `JWKS_URL=http://host.docker.internal:5000/.well-known/jwks`
- WHEN container starts
- THEN `JWKS_URL` env var MUST be available in the application

### RQ-DKR-04: Health Check

The system MUST expose `GET /api/auth/health` returning `{"status": "ok"}` for Docker health check and Railway monitoring.

#### Scenario: Health check response

- GIVEN a running container
- WHEN GET /api/auth/health is called
- THEN response MUST be 200 with `{"status": "ok"}`
- AND response time MUST be < 500ms

### RQ-DKR-05: .dockerignore

The system MUST provide a `.dockerignore` excluding `__pycache__`, `.venv`, `.git`, `output/`, `jobs.db`, `.env`, and `tests/`.

#### Scenario: Build context size

- GIVEN the `.dockerignore` file
- WHEN `docker build` is executed
- THEN build context MUST NOT include excluded directories

## Dependencies

- **Infra**: Docker Engine 24+, Docker Compose v2+
- **Config**: `.env.docker` with all required env vars

## Acceptance Criteria

- [ ] `docker build` succeeds and creates a < 500MB image
- [ ] `docker compose up` starts and serves API in < 10s
- [ ] Health endpoint returns 200 from inside container
- [ ] Volume mounts persist generated output and DB across restarts
- [ ] `.env.docker` has sensible defaults for local dev
