# ADR-004: Python and FastAPI backend

**Decision:** The server and CLI use Python, with FastAPI for the HTTP/WebSocket API.

**Consequences:** Public API behavior is described by FastAPI's OpenAPI document and tested through the app boundary.
