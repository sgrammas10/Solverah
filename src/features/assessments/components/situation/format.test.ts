import { splitFirstSentence } from "./format";

describe("splitFirstSentence", () => {
  it("splits a paragraph into its first sentence and the rest", () => {
    expect(
      splitFirstSentence(
        "You would rather make a known thing work properly. An underrated match: depth compounds.",
      ),
    ).toEqual([
      "You would rather make a known thing work properly.",
      "An underrated match: depth compounds.",
    ]);
  });

  it("returns the whole text as the lead when there is one sentence", () => {
    expect(splitFirstSentence("Much the same tempo, and worth protecting.")).toEqual([
      "Much the same tempo, and worth protecting.",
      "",
    ]);
  });

  it("does not split on a full stop followed by lowercase", () => {
    expect(splitFirstSentence("Short cycles, e.g. weekly ships. Then the rest.")).toEqual([
      "Short cycles, e.g. weekly ships.",
      "Then the rest.",
    ]);
  });

  it("splits before an opening quotation mark", () => {
    expect(splitFirstSentence("It fits. “Steady” is the word.")).toEqual([
      "It fits.",
      "“Steady” is the word.",
    ]);
  });
});
