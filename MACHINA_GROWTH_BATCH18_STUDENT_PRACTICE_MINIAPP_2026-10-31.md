# MACHINA Growth Batch 18 — Student Practice Mini App Integration

Date: 2026-10-31
Base: Batch 17 Full Audit + Visual Finish

## Scope
Connected the previously intentional exception (student multiple-choice exams and essay practice) to the Mini App, while keeping it visually and functionally separate from the lawyer workbench and AI submenu.

## Reused source data and behavior
- Uses the same local `student_quiz.json` and `student_essay.json` files already consumed by the Telegram bot.
- Eight study-year levels are exposed.
- 37 MCQ course groups containing 685 existing questions; each attempt selects up to 10 questions at random, matching the Telegram bot's 10-question flow.
- Five essay categories containing 12 existing prompts; each attempt selects up to five prompts at random, matching the bot's existing flow.
- MCQ feedback includes correctness and the existing explanation.
- Essay sample answers are returned only after the user explicitly requests them; moving to the next question remains available without revealing the sample.
- No AI provider, AI credits, or external model calls are used.
- Registration is required, matching the Telegram bot's `_require_registered` gate.

## Mini App presentation
- Added a distinct `ACADEMIC PRACTICE` area beneath the lawyer tools grid.
- Added separate MCQ and essay entry flows, year/course selection, progress display, answer feedback, sample-answer reveal, and end-of-session state.
- Applied the existing light green / steel / champagne design language with an academic-specific card treatment; no generated images or heavy animations.

## API
- `GET /api/v1/student-practice/catalog`
- `GET /api/v1/student-practice/catalog?level=<level_id>`
- `POST /api/v1/student-practice/start`
- `POST /api/v1/student-practice/answer`
- `POST /api/v1/student-practice/essay-sample`
- `POST /api/v1/student-practice/essay-next`

Sessions are stored server-side, bound to the authenticated Telegram user, expire after one hour of inactivity, and use per-question tokens to reject stale or replayed buttons. Correct answers and essay sample text are not included in the initial question payload. Sessions are intentionally ephemeral; a server restart ends an active practice session.

## Verification
- Full test suite: **295 passed**.
- Python compileall: PASS.
- `node --check miniapp/app.js`: PASS.
- `preflight.py`: PASS.
- API tests cover registered-user gating, session ownership, answer privacy, stale question-token rejection, essay sample privacy, and next-question flow.

## Not performed
- No live Telegram WebView test or real-device visual inspection was performed in this environment.
- Existing student question and sample-answer content was reused as-is; this batch did not independently validate the substantive accuracy of every educational item against current legislation or university syllabi.
- In-memory practice sessions do not survive API process restarts and are not shared between multiple independent API worker processes.
