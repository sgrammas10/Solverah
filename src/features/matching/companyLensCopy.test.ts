/**
 * The words CompanyLens builds from the wire's direction and tolerance fields, and
 * the polling schedule. The direction convention is the server's: `more` = further
 * toward the high pole than the user prefers.
 */
import {
  coverageDetail,
  coverageLine,
  dateRange,
  directionPhrase,
  disagreementPhrase,
  flagCountLines,
  joinNames,
  knownReadLine,
} from "./companyLensCopy";
import { pollDelay } from "./usePoll";

const PACE = { low_pole: "steady", high_pole: "fast" };

describe("directionPhrase", () => {
  it("puts `more` on the high pole and `less` on the low pole", () => {
    expect(directionPhrase("more", PACE)).toBe("More on the fast side than you prefer");
    expect(directionPhrase("less", PACE)).toBe("More on the steady side than you prefer");
    expect(directionPhrase("even", PACE)).toBe("About where you prefer");
    expect(directionPhrase(null, PACE)).toBe("");
  });
});

describe("knownReadLine", () => {
  it("adds inside or outside your give, except when even", () => {
    expect(knownReadLine({ ...PACE, direction: "more", within_tolerance: true })).toBe(
      "More on the fast side than you prefer, inside your give",
    );
    expect(knownReadLine({ ...PACE, direction: "less", within_tolerance: false })).toBe(
      "More on the steady side than you prefer, outside your give",
    );
    expect(knownReadLine({ ...PACE, direction: "even", within_tolerance: true })).toBe(
      "About where you prefer",
    );
  });
});

describe("coverage", () => {
  it("counts known and mixed traits as read, and spells out the rest", () => {
    const coverage = { known: 3, mixed: 1, unknown: 2, total: 6 };
    expect(coverageLine(coverage)).toBe("Based on 4 of 6 traits");
    expect(coverageDetail(coverage)).toBe(
      "3 clear, 1 where the evidence disagrees, 2 with too little evidence",
    );
  });
});

describe("flagCountLines", () => {
  it("leaves out zero counts and pluralises", () => {
    expect(flagCountLines({ must_have_breaks: 2, risks: 0, investigate: 1 })).toEqual([
      "2 must-haves outside your give",
      "1 to find out about",
    ]);
    expect(flagCountLines({ must_have_breaks: 0, risks: 0, investigate: 0 })).toEqual([]);
  });
});

describe("disagreementPhrase", () => {
  it("names the pole the posting leans toward when the directions differ", () => {
    expect(disagreementPhrase("Autonomy", "less", "more", { low_pole: "directed", high_pole: "self-directed" })).toBe(
      "This posting describes autonomy as more on the self-directed side than the company evidence does.",
    );
    expect(disagreementPhrase("Pace", "more", "even", PACE)).toBe(
      "This posting describes pace as more on the steady side than the company evidence does.",
    );
  });

  it("only says they differ when both lean the same way", () => {
    expect(disagreementPhrase("Pace", "more", "more", PACE)).toBe(
      "This posting and the company evidence describe pace differently.",
    );
  });
});

describe("small helpers", () => {
  it("joins names in plain English", () => {
    expect(joinNames([])).toBe("");
    expect(joinNames(["Pace"])).toBe("Pace");
    expect(joinNames(["Pace", "Feedback", "Autonomy"])).toBe("Pace, Feedback and Autonomy");
  });

  it("collapses a one-month date range", () => {
    expect(dateRange("2025-06-01", "2025-06-20")).toBe(dateRange("2025-06-01", null));
    expect(dateRange(null, null)).toBe("");
    expect(dateRange("2024-01-10", "2025-06-01")).toContain(" to ");
  });
});

describe("pollDelay", () => {
  it("starts at 3 s and backs off to a ceiling", () => {
    const timing = { initialMs: 3000, factor: 1.5, maxMs: 20000 };
    expect(pollDelay(0, timing)).toBe(3000);
    expect(pollDelay(1, timing)).toBe(4500);
    expect(pollDelay(2, timing)).toBe(6750);
    expect(pollDelay(10, timing)).toBe(20000);
  });
});
