# Reference

## API

The FastAPI application exposes OpenAPI at `/openapi.json`. The `/api/v1` compatibility prefix aliases the version-one REST paths while `/api` remains available for local compatibility.

Important groups include projects/pipelines, generation and validation, runs/events, debug analysis, secrets, schedules, Git, runtime profiles, and collaboration WebSockets.

## Configuration

- `SDPSTUDIO_DATA_ROOT` — local data root.
- `SDPSTUDIO_DATABASE_URL` — optional team database URL.
- `SDPSTUDIO_AUTH_SIGNING_KEY` — session signing key.
- `SDPSTUDIO_SECRET_KEY` — secret-vault key material.
- `SDPSTUDIO_HISTORY_MAX_COUNT` / `SDPSTUDIO_HISTORY_MAX_AGE_DAYS` — local-history retention.
- Provider review credentials are stored in the SDP Studio secrets vault under `provider.github.token` or `provider.gitlab.token`; provider APIs reject environment-only tokens.

See the OpenAPI document and the runtime-profile API models for the authoritative request/response shapes.
