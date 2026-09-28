/**
 * LegalPage.tsx — Renders the Privacy Policy or Terms of Service from
 * shared/lib/legal.ts (the in-app source of truth for legal text).
 *
 * Used by the /privacy and /terms routes in App.tsx. Public — no auth.
 *
 * The document's own "# Title" becomes the page title, and every "## " heading
 * becomes a section with an anchor id and an entry in the table of contents.
 * Both the contents and the headings take their ids from sectionId(), so they
 * cannot drift apart when the text is edited.
 *
 * While LEGAL_IS_DRAFT is true a visible "under review" notice renders so the
 * draft status is never silently presented as final.
 */
import { ReactNode, isValidElement } from "react";
import ReactMarkdown from "react-markdown";
import {
  LEGAL_IS_DRAFT,
  LEGAL_LAST_UPDATED,
  PRIVACY_POLICY_MD,
  TERMS_OF_SERVICE_MD,
} from "../../../shared/lib/legal";
import { sectionId } from "../../../shared/lib/sectionId";
import DocLayout, { DocSection } from "../../../shared/ui/DocLayout";
import { DOC_H2, DOC_P } from "../../../shared/ui/publicStyles";

interface ParsedDoc {
  title: string;
  body: string;
  sections: DocSection[];
}

function parseDoc(md: string): ParsedDoc {
  const lines = md.trim().split("\n");
  const titleLine = lines[0].startsWith("# ") ? lines.shift()! : "";
  const sections = lines
    .filter((line) => line.startsWith("## "))
    .map((line) => {
      // Numbers stay in the contents: the Terms cross-reference sections by number.
      const title = line.slice(3).trim();
      return { id: sectionId(title), title };
    });
  return { title: titleLine.slice(2).trim(), body: lines.join("\n"), sections };
}

/** Plain text of a rendered markdown node, for deriving a heading's id. */
function textOf(node: ReactNode): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join("");
  if (isValidElement<{ children?: ReactNode }>(node)) return textOf(node.props.children);
  return "";
}

const RELATED = [
  { to: "/privacy", label: "Privacy policy" },
  { to: "/terms", label: "Terms of service" },
  { to: "/how-matching-works", label: "How matching works" },
];

function DraftNotice() {
  return (
    <div role="note" className="mb-10 border-l-[3px] border-forest-dark bg-white px-5 py-4">
      <p className="text-[0.95rem] font-semibold text-ink-primary">Draft under legal review</p>
      <p className="mt-1 text-[0.95rem] leading-[1.6] text-ink-secondary">
        This document describes how Solverah works today. Its wording may be refined before the
        effective date is set.
      </p>
    </div>
  );
}

function LegalPage({ doc }: { doc: "privacy" | "terms" }) {
  const { title, body, sections } = parseDoc(
    doc === "privacy" ? PRIVACY_POLICY_MD : TERMS_OF_SERVICE_MD,
  );

  return (
    <DocLayout
      title={title}
      meta={`Last updated ${LEGAL_LAST_UPDATED}`}
      back={{ to: "/", label: "Back to Solverah" }}
      notice={LEGAL_IS_DRAFT ? <DraftNotice /> : null}
      sections={sections}
      related={RELATED.filter((l) => l.to !== `/${doc}`)}
    >
      <ReactMarkdown
        components={{
          h2: ({ children }) => (
            <h2 id={sectionId(textOf(children))} className={`${DOC_H2} mb-4 mt-14`}>
              {children}
            </h2>
          ),
          p: ({ children }) => <p className={`${DOC_P} mb-5`}>{children}</p>,
          ul: ({ children }) => (
            <ul className={`${DOC_P} mb-5 list-disc space-y-2.5 pl-6 marker:text-ink-tertiary`}>
              {children}
            </ul>
          ),
          strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
          a: ({ href, children }) => (
            <a
              href={href}
              className="font-medium text-forest-mid underline underline-offset-4 transition-colors hover:text-forest-dark"
            >
              {children}
            </a>
          ),
        }}
      >
        {body}
      </ReactMarkdown>
    </DocLayout>
  );
}

export default LegalPage;
