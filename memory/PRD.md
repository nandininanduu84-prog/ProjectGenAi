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
## Implemented (2026-06)
- Fixed AI generation/refine/chat returning identical generic (mock) results: root cause was provider 429 concurrent_request_limit errors silently falling back to mock_projects template.
- Fix in /app/backend/server.py: asyncio.Semaphore(1) serializes all LLM calls, 4 retries with backoff on 429/rate-limit, honest 503 "AI mentor is busy" error instead of silent mock (mock only used when EMERGENT_LLM_KEY is absent).
- Verified via curl on external URL: two distinct generations for different inputs, refine returns modified project, chat returns contextual answer.

## Backlog
- P0: Verify Google OAuth end-to-end in a real browser (entry point + callback exist, provider completion untested).
- P1: Full browser regression via testing agent (history filters, PDF, mobile nav, admin).
- P2: Split compact App.js into page components before large future changes.

## Implemented (2026-06, iteration 2)
- Verified via testing agent (iteration_2.json, 13/13 backend, 100% frontend): AI bug fixed — distinct topic-specific generations, refine/chat working.
- New: Idea Comparison (select 2 cards on dashboard/history -> /compare side-by-side view with Choose buttons).
- New: Viva Prep Mode (POST /api/ai/viva, VivaBox on details page, ~8 expandable Q&A items).
- History page fixed: cards now open details, delete button added, compare enabled.
- Google sign-in: redirect to managed auth verified + invalid-session graceful fallback to /login (full provider completion not automatable).
- Fixed legacy dict tech_stack (normalize on read in GET /api/projects + frontend Array.isArray guard by testing agent).
- Dashboard stats now show real counts instead of hardcoded 12/4/08.

## Backlog
- P2: Real popular-branches data in /api/admin/stats (currently static 42/28/24 list).
- P2: Split compact App.js into page components before large future changes.

## Implemented (2026-06, iteration 3)
- Testing agent (iteration_3.json, 100% backend + frontend): count honored (3/5/10), outputs input-specific, mock template fully removed, 503 visible errors on AI failure.
- User asked to "replace Gemini key with Universal Key": verified NO Gemini key exists; app already uses EMERGENT_LLM_KEY (GPT 5.4 Mini) server-side. No change needed.

## Backlog (from iteration_3 review)
- P2: raise 503 if final idea count < requested after top-up loop.
- P2: remove dead ternary in generate response; require JWT_SECRET from env.
- P2: add data-testid to interests input; explicit value prop on <option>.

## Implemented (2026-06, iteration 5) - Groq migration
- Replaced Emergent Universal Key with user's Groq API key (GROQ_API_KEY + GROQ_MODEL=openai/gpt-oss-120b in backend/.env); emergentintegrations removed from server.py; portable to external hosting.
- Groq free tier = 8000 TPM: single lean AI call per generation (max_completion_tokens=7000, reasoning_effort=low, concise-output prompt), parse_ideas salvages truncated JSON, 413/429 backoff retries.
- Verified by testing agent iteration_5 (100%): count 3/5/10 all exact + topic-specific (4-9s), refine, viva=8, frontend e2e count=5, no option hydration warnings.
- Hardening: JWT_SECRET now required from env (no fallback); current_user raises 401 on malformed token sub; regression suite /app/backend/tests/test_retest_iter5.py (space generate calls 60s apart due to TPM).
- Note: partial under-delivery returns actual ideas; frontend toast announces real count (not silent).
