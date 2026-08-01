> **Note:** Summary files are incrementally appended. This entry covers the work completed for **Card 28: AI-1220 — AI Chat Interface**.

# Summary 21 — Card 28: AI-1220 AI Chat Interface

## What Was Done

Built a tenant-scoped, session-aware AI chat interface on top of the existing chat models and LLM client. Users can now create chat sessions, send messages that maintain conversation context, list sessions, retrieve full message history, get suggested follow-up questions, and delete sessions. The implementation is read-only with respect to financial data and falls back to deterministic responses when the LLM is unavailable.

## Key Changes

- Rewrote `app/services/ai_chat.py`:
  - `AIChatService` with `list_sessions`, `get_session`, `get_chat_history`, `delete_session`
  - `_get_or_create_session` creates sessions and auto-generates titles
  - `_build_history` loads the last 100 messages and sends the last 10 to the LLM prompt
  - `_generate_response` uses `LLMClient`, `CostController`, and `SafetyFilter`
  - `_rule_based_response` provides deterministic fallback answers and actions
  - `_suggested_questions` and `_suggested_questions_from_history` return topic-aware follow-ups
- Updated `app/ai_cfo/llm/prompts.py`:
  - `chat_prompt()` now accepts `history: list[dict[str, str]]` and includes prior messages
- Extended `app/schemas/ai.py`:
  - `ChatMessageResponse`, `ChatSessionResponse`, `ChatSessionsResponse`
  - `ChatHistoryResponse`, `ChatSuggestedQuestionsResponse`
  - `session_id` added to `ChatResponse`
- Extended `app/routers/ai.py` with session routes:
  - `GET /ai/chat/sessions`
  - `GET /ai/chat/sessions/{session_id}`
  - `GET /ai/chat/sessions/{session_id}/messages`
  - `GET /ai/chat/sessions/{session_id}/suggested-questions`
  - `DELETE /ai/chat/sessions/{session_id}`
- Updated `POST /ai/chat` to return `session_id` and maintain session context.
- Added `app/tests/integration/test_ai_chat.py` with 10 tests covering auth, session creation, history, suggested questions, deletion, cross-tenant isolation, and LLM fallback.

## Verification

- `python -m compileall app` — OK
- `alembic current` — `5e8169dd3017`
- `alembic upgrade head` — OK
- `python scripts/inspect_db.py` — OK
- `python scripts/seed_default_data.py --dev` — OK
- `python -m pytest -q` — **364 passed, 1 skipped**

## Next Recommended Card

**AI-1221 — AI Memory System**
