/**
 * quizPayload.ts — one place that knows where each quiz's answers and insights
 * live on the profile document, and how to turn them into a request.
 *
 * Six quizzes, two answer homes (unchanged, and the server merges both):
 *   - the four career quizzes: `quizResults.careerQuizzes.<key>`
 *   - Career & Job Search and Your Future, Your Way: `quizResults.<key>`
 *
 * One insight home (2026-10-02 audit #7 / G16): every quiz's insight is
 * `quizInsights.careerQuizzes.<key>`, with the group's `_overallInsight` as the
 * "Across all your quizzes" card. Before this, signed-in writes nested there
 * while the guest replay wrote a flat `quizInsights.<key>`, and the two
 * stand-alone quizzes read only the flat key -- so a stored insight never
 * preloaded and a replayed one never showed under /quiz-insights. The flat key
 * is still READ as a fallback, for documents written before the fix.
 *
 * Every signed-in insight request carries every saved quiz (audit #6): the
 * server's cross-quiz synthesis can only be "across all your quizzes" if it
 * was shown all of them.
 */
import { careerQuizzes } from "./data/careerQuizzes";
import { nextChapterSections } from "./data/nextChapterYourWayQuiz";
import { yourFutureYourWayQuestions } from "./data/solverahYourFutureYourWayQuiz";
import type { QuizInsight } from "./useQuizInsight";

export const CAREER_QUIZ_GROUP = "careerQuizzes";
export const CAREER_JOB_SEARCH_KEY = "careerJobSearch";
export const YOUR_FUTURE_KEY = "yourFutureYourWay";

/** questionId -> selected option index. JSON round trips make the keys strings. */
export type QuizAnswers = Record<number, number>;

export type QuizDefinition = {
  key: string;
  title: string;
  questions: { id: number; text: string; options: string[] }[];
  /** True when the answers live under `quizResults.careerQuizzes.<key>`. */
  nestedAnswers: boolean;
};

export type QuizRequestPayload = {
  quizGroup: string;
  quizzes: { key: string; title: string; items: { question: string; selected: string }[] }[];
};

export const ALL_QUIZZES: QuizDefinition[] = [
  ...careerQuizzes.map((quiz) => ({ ...quiz, nestedAnswers: true })),
  {
    key: CAREER_JOB_SEARCH_KEY,
    title: "Career & Job Search",
    questions: nextChapterSections.flatMap((section) => section.questions),
    nestedAnswers: false,
  },
  {
    key: YOUR_FUTURE_KEY,
    title: "Your Future, Your Way",
    questions: yourFutureYourWayQuestions,
    nestedAnswers: false,
  },
];

const asRecord = (value: unknown): Record<string, any> | null =>
  value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, any>) : null;

/** True when at least one question has a valid selected option. */
export function hasAnswers(answers: unknown): boolean {
  const record = asRecord(answers);
  return Boolean(record && Object.values(record).some((v) => typeof v === "number"));
}

/** The {question, selected} items for one quiz; unanswered questions are skipped. */
export function quizItems(quiz: Pick<QuizDefinition, "questions">, answers: unknown) {
  const record = asRecord(answers) ?? {};
  return quiz.questions.flatMap((q) => {
    const idx = record[q.id];
    const selected = typeof idx === "number" ? q.options[idx] : undefined;
    return selected ? [{ question: q.text, selected }] : [];
  });
}

/** The answers one quiz has saved in a `quizResults` document. */
export function answersFor(quizResults: unknown, quiz: QuizDefinition): QuizAnswers | null {
  const results = asRecord(quizResults);
  if (!results) return null;
  const value = quiz.nestedAnswers ? asRecord(results[CAREER_QUIZ_GROUP])?.[quiz.key] : results[quiz.key];
  return hasAnswers(value) ? (value as QuizAnswers) : null;
}

/**
 * The request for every quiz answered in `quizResults`, in ALL_QUIZZES order.
 * Quizzes with no answered items are left out; `quizzes` may come back empty,
 * which the caller must treat as "nothing to send".
 */
export function buildAllQuizzesPayload(quizResults: unknown): QuizRequestPayload {
  return {
    quizGroup: CAREER_QUIZ_GROUP,
    quizzes: ALL_QUIZZES.flatMap((quiz) => {
      const items = quizItems(quiz, answersFor(quizResults, quiz));
      return items.length ? [{ key: quiz.key, title: quiz.title, items }] : [];
    }),
  };
}

/** The request for one quiz's answers alone (the guest preview takes one quiz). */
export function buildSingleQuizPayload(quiz: QuizDefinition, answers: unknown): QuizRequestPayload {
  const items = quizItems(quiz, answers);
  return {
    quizGroup: CAREER_QUIZ_GROUP,
    quizzes: items.length ? [{ key: quiz.key, title: quiz.title, items }] : [],
  };
}

export function quizDefinition(key: string): QuizDefinition | undefined {
  return ALL_QUIZZES.find((quiz) => quiz.key === key);
}

/**
 * One quiz's stored insight: `quizInsights.careerQuizzes.<key>`, else the
 * legacy flat `quizInsights.<key>` document written before 2026-10-02.
 */
export function storedInsightFor(quizInsights: unknown, key: string): QuizInsight | null {
  const insights = asRecord(quizInsights);
  if (!insights) return null;
  const entry = asRecord(asRecord(insights[CAREER_QUIZ_GROUP])?.[key]) ?? asRecord(insights[key]);
  if (!entry || (!entry.summary && !entry.keyTakeaways && !entry.nextSteps)) return null;
  return {
    key,
    title: entry.title,
    summary: entry.summary,
    keyTakeaways: Array.isArray(entry.keyTakeaways) ? entry.keyTakeaways : undefined,
    combinedMeaning: entry.combinedMeaning,
    nextSteps: Array.isArray(entry.nextSteps) ? entry.nextSteps : undefined,
  };
}

/** The career group's stored cross-quiz synthesis, if any. */
export function storedOverallInsight(quizInsights: unknown) {
  const overall = asRecord(asRecord(asRecord(quizInsights)?.[CAREER_QUIZ_GROUP])?._overallInsight);
  return overall
    ? {
        summary: typeof overall.summary === "string" ? overall.summary : undefined,
        keyTakeaways: Array.isArray(overall.keyTakeaways) ? overall.keyTakeaways : undefined,
        nextSteps: Array.isArray(overall.nextSteps) ? overall.nextSteps : undefined,
      }
    : null;
}
