---
name: agent-and-quiz-cost-caps
description: Server-side model lock and the token/length caps on /agent/messages and both quiz-insight endpoints (2026-10-02), with the reasoning behind each number
metadata:
  type: project
---

Decided 2026-10-02 (Sebastian's recommended answer: yes to the server-side lock).

- Agent model: server only (`llm.default_agent_model()`, SOLVERAH_AGENT_MODEL
  else openai/gpt-oss-20b). Client `model` is dropped by extra="ignore".
  `test_agent_chat_custom_model` was replaced because it enshrined the old
  client-chosen behaviour.
- Agent: roles user/assistant only (system -> 422), 40 messages x 4,000 chars
  (schema), 16,000-char history budget trimmed oldest-first
  (`agent_service.bounded_history`), max_completion_tokens 1,500 (includes
  gpt-oss reasoning tokens). SPA sends the last 20 turns.
- Quiz insights (signed-in AND guest share QuizInsightsRequest): 8 quizzes,
  40 items/quiz, question 400 / selected 300 chars, 120 items total (service
  400), max_completion_tokens 4,000. The six real quizzes total 78 items.
- Model-not-found is now 503 `agent_model_unavailable` (was 422): the model is
  the server's choice, so it is our outage.

**Why:** the guest endpoint was an anonymous LLM proxy and the agent let any
browser pick the most expensive Groq model on our key.
**How to apply:** a new quiz that exceeds these caps must raise them in
`schemas/intelligence.py` and `insight_service.MAX_TOTAL_ITEMS` together;
`quizPayload.test.ts` checks the real quizzes fit. Related [[quiz-insight-storage-home]].
