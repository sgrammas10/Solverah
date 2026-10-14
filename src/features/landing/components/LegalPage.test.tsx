/**
 * LegalPage — the table of contents and the headings it points at.
 *
 * What can break: a contents entry whose anchor matches no heading (the link
 * silently does nothing), a section missing from the contents, or the draft
 * notice disappearing while the text is still a draft.
 */
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import LegalPage from "./LegalPage";
import {
  LEGAL_IS_DRAFT,
  LEGAL_LAST_UPDATED,
  PRIVACY_POLICY_MD,
  TERMS_OF_SERVICE_MD,
} from "../../../shared/lib/legal";

function renderLegal(doc: "privacy" | "terms") {
  render(
    <MemoryRouter>
      <LegalPage doc={doc} />
    </MemoryRouter>,
  );
}

function headingsIn(md: string): string[] {
  return md
    .split("\n")
    .filter((line) => line.startsWith("## "))
    .map((line) => line.slice(3).trim());
}

describe.each([
  ["privacy", PRIVACY_POLICY_MD, "Privacy Policy"],
  ["terms", TERMS_OF_SERVICE_MD, "Terms of Service"],
] as const)("LegalPage (%s)", (doc, md, title) => {
  it("renders the document title as the page's only h1, with a last-updated line", () => {
    renderLegal(doc);
    const h1s = screen.getAllByRole("heading", { level: 1 });
    expect(h1s).toHaveLength(1);
    expect(h1s[0]).toHaveTextContent(title);
    expect(screen.getByText(`Last updated ${LEGAL_LAST_UPDATED}`)).toBeInTheDocument();
  });

  it("lists every section in the contents, in order", () => {
    renderLegal(doc);
    const toc = screen.getByRole("navigation", { name: "Contents" });
    const labels = within(toc)
      .getAllByRole("link")
      .map((a) => a.textContent);
    expect(labels).toEqual(headingsIn(md));
  });

  it("points every contents link at a heading with that id", () => {
    renderLegal(doc);
    const toc = screen.getByRole("navigation", { name: "Contents" });
    for (const link of within(toc).getAllByRole("link")) {
      const href = link.getAttribute("href")!;
      expect(href).toMatch(/^#[a-z0-9-]+$/);
      const target = document.getElementById(href.slice(1));
      expect(target).not.toBeNull();
      expect(target!.tagName).toBe("H2");
      expect(target).toHaveTextContent(link.textContent!);
    }
  });

  it("gives mobile readers the same contents", () => {
    renderLegal(doc);
    const desktop = within(screen.getByRole("navigation", { name: "Contents" }))
      .getAllByRole("link")
      .map((a) => a.getAttribute("href"));
    const mobile = within(screen.getByRole("navigation", { name: "Contents, mobile" }))
      .getAllByRole("link")
      .map((a) => a.getAttribute("href"));
    expect(mobile).toEqual(desktop);
  });

  it("shows the draft notice exactly while the text is a draft", () => {
    renderLegal(doc);
    const notice = screen.queryByRole("note");
    if (LEGAL_IS_DRAFT) {
      expect(notice).toHaveTextContent(/draft under legal review/i);
    } else {
      expect(notice).toBeNull();
    }
  });

  it("does not link the page to itself in the related links", () => {
    renderLegal(doc);
    const related = screen.getByRole("navigation", { name: "Related pages" });
    for (const link of within(related).getAllByRole("link")) {
      expect(link).not.toHaveAttribute("href", `/${doc}`);
    }
  });
});

it("drops the section number from anchors but keeps it in the contents", () => {
  renderLegal("terms");
  const toc = screen.getByRole("navigation", { name: "Contents" });
  const link = within(toc).getByRole("link", { name: "1. Who can use Solverah" });
  expect(link).toHaveAttribute("href", "#who-can-use-solverah");
});

it("says nothing about early access in either document", () => {
  expect(PRIVACY_POLICY_MD).not.toMatch(/early[- ]access|waitlist|launch period/i);
  expect(TERMS_OF_SERVICE_MD).not.toMatch(/early[- ]access|waitlist|launch period/i);
});
