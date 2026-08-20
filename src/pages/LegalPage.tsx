/**
 * LegalPage.tsx — Renders the Privacy Policy or Terms of Service from
 * src/data/legal.ts (the in-app source of truth for legal text).
 *
 * Used by the /privacy and /terms routes in App.tsx. Public — no auth.
 * While LEGAL_IS_DRAFT is true a visible "under review" banner renders so the
 * draft status is never silently presented as final.
 */
import ReactMarkdown from "react-markdown";
import { Link } from "react-router-dom";
import {
  LEGAL_IS_DRAFT,
  PRIVACY_POLICY_MD,
  TERMS_OF_SERVICE_MD,
} from "../data/legal";

function LegalPage({ doc }: { doc: "privacy" | "terms" }) {
  const content = doc === "privacy" ? PRIVACY_POLICY_MD : TERMS_OF_SERVICE_MD;

  return (
    <main className="min-h-screen bg-cream-base font-sans">
      <div className="mx-auto max-w-3xl px-6 py-16">
        <Link
          to="/"
          className="inline-flex items-center gap-1.5 text-sm text-ink-tertiary hover:text-forest-mid transition-colors mb-8"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <path d="M10 12L6 8l4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          Back to Solverah
        </Link>

        {LEGAL_IS_DRAFT && (
          <div
            role="note"
            className="mb-8 rounded border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900"
          >
            This document is a draft undergoing legal review. Its substance
            reflects how Solverah actually operates today; wording may be
            refined before the effective date is set.
          </div>
        )}

        <article>
          <ReactMarkdown
            components={{
              h1: (props) => (
                <h1 className="font-display text-3xl font-bold text-ink-primary mb-6" {...props} />
              ),
              h2: (props) => (
                <h2 className="font-display text-xl font-semibold text-ink-primary mt-10 mb-3" {...props} />
              ),
              p: (props) => (
                <p className="text-sm text-ink-secondary leading-relaxed mb-4" {...props} />
              ),
              ul: (props) => (
                <ul className="list-disc pl-6 mb-4 space-y-2 text-sm text-ink-secondary leading-relaxed" {...props} />
              ),
              li: (props) => <li {...props} />,
              strong: (props) => (
                <strong className="font-semibold text-ink-primary" {...props} />
              ),
              a: (props) => (
                <a
                  className="underline text-forest-mid hover:text-forest-dark transition-colors"
                  {...props}
                />
              ),
            }}
          >
            {content}
          </ReactMarkdown>
        </article>

        <div className="mt-12 border-t border-cream-muted pt-6 flex gap-6">
          <Link to="/privacy" className="text-xs text-ink-tertiary underline hover:text-forest-mid">
            Privacy Policy
          </Link>
          <Link to="/terms" className="text-xs text-ink-tertiary underline hover:text-forest-mid">
            Terms of Service
          </Link>
          <Link to="/how-matching-works" className="text-xs text-ink-tertiary underline hover:text-forest-mid">
            How matching works
          </Link>
        </div>
      </div>
    </main>
  );
}

export default LegalPage;
