
# WhatIf Mobility

## Project Goal
Build an AI-powered urban public transport
simulation application.

Users describe hypothetical changes to a
city bus network using natural language.
The system simulates their impact on
passenger journeys.

## Technology Stack

Frontend:
- React
- TypeScript
- Vite
- Tailwind CSS
- React Leaflet
- Axios
- Recharts

Backend:
- Python
- FastAPI
- SQLAlchemy
- Pydantic
- SQLite
- NetworkX
- Pytest

## Architecture
- Separate frontend and backend.
- Use REST API.
- Keep business logic in service modules.
- Use Pydantic for validation.
- Use SQLAlchemy for database operations.
- Keep AI logic separate from simulation logic.

## Simulation Rules
- Represent transport networks as directed graphs.
- Stops are graph nodes.
- Connections are graph edges.
- Edge weights represent travel time.
- Each simulation must use a copy of baseline data.
- Never modify baseline data during simulation.
- Calculate all metrics deterministically.
- AI must never invent simulation results.

## Coding Standards
- Use Python type hints.
- Use TypeScript types.
- Write readable and maintainable code.
- Handle errors explicitly.
- Avoid unnecessary dependencies.
- Write tests for important business logic.

## Development Workflow
Before implementing a feature:
1. Inspect the existing code.
2. Explain the implementation plan.
3. Identify affected files.
4. Wait for approval for substantial changes.

After implementation:
1. Run tests.
2. Check for errors.
3. Explain changed files.
4. Report remaining issues.

## Important
- Never hardcode API keys.
- Never commit .env files.
- Do not generate fake simulation metrics.
- Do not rewrite unrelated code.
- Explain important technical decisions.