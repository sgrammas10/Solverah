import {
  ALL_QUIZZES,
  buildAllQuizzesPayload,
  buildSingleQuizPayload,
  quizDefinition,
  storedInsightFor,
} from "./quizPayload";

describe("buildAllQuizzesPayload", () => {
  it("reads nested career answers and flat stand-alone answers, in quiz order", () => {
    const payload = buildAllQuizzesPayload({
      yourFutureYourWay: { 1: 0 },
      careerQuizzes: { midCareer: { 1: 1 }, earlyCareer: { 1: 0, 2: 3 } },
      careerJobSearch: { "1": 2 },
    });
    expect(payload.quizGroup).toBe("careerQuizzes");
    expect(payload.quizzes.map((q) => [q.key, q.items.length])).toEqual([
      ["earlyCareer", 2],
      ["midCareer", 1],
      ["careerJobSearch", 1],
      ["yourFutureYourWay", 1],
    ]);
  });

  it("leaves out quizzes with nothing answered", () => {
    expect(buildAllQuizzesPayload({ careerQuizzes: { earlyCareer: {} } }).quizzes).toEqual([]);
    expect(buildAllQuizzesPayload(undefined).quizzes).toEqual([]);
  });

  it("stays inside the server's caps with every quiz fully answered", () => {
    const all: Record<string, any> = { careerQuizzes: {} };
    for (const quiz of ALL_QUIZZES) {
      const answers = Object.fromEntries(quiz.questions.map((q) => [q.id, 0]));
      if (quiz.nestedAnswers) all.careerQuizzes[quiz.key] = answers;
      else all[quiz.key] = answers;
    }
    const payload = buildAllQuizzesPayload(all);
    expect(payload.quizzes.length).toBeLessThanOrEqual(8);
    for (const quiz of payload.quizzes) {
      expect(quiz.items.length).toBeLessThanOrEqual(40);
      for (const item of quiz.items) {
        expect(item.question.length).toBeLessThanOrEqual(400);
        expect(item.selected.length).toBeLessThanOrEqual(300);
      }
    }
    expect(payload.quizzes.reduce((n, q) => n + q.items.length, 0)).toBeLessThanOrEqual(120);
  });
});

describe("buildSingleQuizPayload", () => {
  it("is empty when nothing is answered", () => {
    expect(buildSingleQuizPayload(quizDefinition("earlyCareer")!, {}).quizzes).toEqual([]);
  });
});

describe("storedInsightFor", () => {
  it("prefers the nested career entry over a legacy flat one", () => {
    const insight = storedInsightFor(
      {
        careerQuizzes: { careerJobSearch: { summary: "Nested." } },
        careerJobSearch: { summary: "Flat." },
      },
      "careerJobSearch",
    );
    expect(insight?.summary).toBe("Nested.");
  });

  it("falls back to the legacy flat document", () => {
    expect(storedInsightFor({ yourFutureYourWay: { summary: "Flat." } }, "yourFutureYourWay")?.summary).toBe(
      "Flat.",
    );
  });

  it("drops list fields that are not lists", () => {
    const insight = storedInsightFor(
      { careerQuizzes: { earlyCareer: { summary: "x", keyTakeaways: "str" } } },
      "earlyCareer",
    );
    expect(insight?.keyTakeaways).toBeUndefined();
  });
});
