"""Entry point of the WhatIf Mobility backend.

Run locally (from the backend/ folder):
    uvicorn app.main:app --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# The Vite dev server runs on port 5173. Browsers block requests from one
# origin (localhost:5173) to another (localhost:8000) unless the backend
# explicitly allows it -- that is what CORS configuration does.
ALLOWED_ORIGINS: list[str] = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


class HealthResponse(BaseModel):
    """Shape of the /api/health response (validated by Pydantic)."""

    status: str


app = FastAPI(title="WhatIf Mobility API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Lightweight check that the server is running."""
    return HealthResponse(status="ok")
