# ProjectGen AI PRD

## Original problem statement
Build a complete full-stack AI Project Idea Generator for B.Tech and college students with authentication, tailored project generation, persistence, refinement, chat, PDF export, history, favorites, and admin analytics.

## Architecture decisions
- React frontend with responsive CSS and React Router.
- FastAPI backend with MongoDB via Motor.
- JWT cookie authentication with bcrypt passwords and seeded admin.
- Server-side Emergent LLM integration using GPT 5.4 Mini.

## Personas
- College student planning an academic project.
- Faculty mentor reviewing project scope.
- Admin monitoring usage and content.

## Implemented (2026-03-08)
- Landing, auth, dashboard, generator form, result cards, details view, save, history, favorites route, refinement, contextual chat, PDF print export, and admin stats.
- MongoDB-backed users and projects with protected API routes.

## Backlog
- P0: Add richer saved-project filtering and full admin moderation list.
- P1: Persist chat messages and add downloadable generated PDF file.
- P2: Add refresh tokens, email reset flow, and usage rate limiting.