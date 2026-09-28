/**
 * DocLayout — the long-form public page: legal documents and the transparency
 * pages. Same palette, type and hairline rules as the landing page.
 *
 * With `sections`, a table of contents sits beside the text: a sticky column
 * on wide screens, a collapsible "Contents" box above the text on narrow ones.
 * Every entry is a plain in-page link to the section's anchor id, so the
 * contents work without JavaScript and each section can be linked to directly.
 *
 * The site header and the O*NET footer come from the app shell, not from here.
 */
import { ReactNode, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CONTAINER, LEAD, PAGE_H1 } from "./publicStyles";

export interface DocSection {
  id: string;
  title: string;
}

export interface DocLink {
  to: string;
  label: string;
}

interface DocLayoutProps {
  title: string;
  /** Short line under the title, e.g. "Last updated 28 September 2026". */
  meta?: ReactNode;
  lead?: ReactNode;
  /** Rendered above the text, e.g. a draft notice. */
  notice?: ReactNode;
  back?: DocLink;
  /** Table of contents entries. Omit for a page too short to need one. */
  sections?: DocSection[];
  /** Links to the sibling documents, listed under the text. */
  related?: DocLink[];
  children: ReactNode;
}

/** Tracks which section is on screen, for the contents highlight. */
function useActiveSection(ids: string[]): string | null {
  const [active, setActive] = useState<string | null>(null);
  const key = ids.join("|");

  useEffect(() => {
    if (!ids.length || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible.length) setActive(visible[0].target.id);
      },
      { rootMargin: "-96px 0px -65% 0px" },
    );
    for (const id of ids) {
      const el = document.getElementById(id);
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return active;
}

function ContentsList({ sections, active }: { sections: DocSection[]; active: string | null }) {
  return (
    <ol className="border-l border-cream-muted">
      {sections.map((s) => {
        const current = s.id === active;
        return (
          <li key={s.id}>
            <a
              href={`#${s.id}`}
              aria-current={current ? "location" : undefined}
              className={`-ml-px block border-l-2 py-1.5 pl-4 text-[0.92rem] leading-[1.45] transition-colors ${
                current
                  ? "border-forest-dark font-semibold text-ink-primary"
                  : "border-transparent text-ink-secondary hover:text-forest-mid"
              }`}
            >
              {s.title}
            </a>
          </li>
        );
      })}
    </ol>
  );
}

function DocLayout({ title, meta, lead, notice, back, sections, related, children }: DocLayoutProps) {
  const hasToc = Boolean(sections?.length);
  const active = useActiveSection(hasToc ? sections!.map((s) => s.id) : []);

  return (
    <main className="landing min-h-screen bg-cream-base font-body text-ink-primary antialiased">
      <div className={`${CONTAINER} pb-20 pt-12 md:pb-28 md:pt-16`}>
        {back && (
          <Link
            to={back.to}
            className="text-[0.9rem] font-medium text-ink-secondary transition-colors hover:text-forest-mid"
          >
            {back.label}
          </Link>
        )}

        <header className={`max-w-[68ch] ${back ? "mt-8" : ""}`}>
          <h1 className={PAGE_H1}>{title}</h1>
          {meta && <p className="mt-4 text-[0.9rem] text-ink-secondary">{meta}</p>}
          {lead && <div className={`mt-6 ${LEAD}`}>{lead}</div>}
        </header>

        <div
          className={`mt-12 border-t border-cream-muted pt-10 ${
            hasToc ? "lg:grid lg:grid-cols-[240px_minmax(0,1fr)] lg:gap-16" : ""
          }`}
        >
          {hasToc && (
            <>
              <nav aria-label="Contents" className="hidden lg:block">
                <div className="sticky top-24">
                  <p className="mb-3 text-[0.86rem] font-semibold text-ink-primary">Contents</p>
                  <ContentsList sections={sections!} active={active} />
                </div>
              </nav>

              <details className="mb-10 border border-cream-muted bg-white lg:hidden">
                <summary className="flex cursor-pointer items-center justify-between px-5 py-4 text-[0.95rem] font-semibold">
                  Contents
                  <svg
                    className="lp-plus shrink-0 text-ink-secondary"
                    width="18"
                    height="18"
                    viewBox="0 0 18 18"
                    fill="none"
                    aria-hidden="true"
                  >
                    <path d="M9 3v12M3 9h12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                  </svg>
                </summary>
                <nav aria-label="Contents, mobile" className="px-5 pb-4">
                  <ContentsList sections={sections!} active={active} />
                </nav>
              </details>
            </>
          )}

          <div className="min-w-0 max-w-[68ch]">
            {notice}
            <article>{children}</article>

            {related?.length ? (
              <nav
                aria-label="Related pages"
                className="mt-16 flex flex-wrap gap-x-8 gap-y-3 border-t border-cream-muted pt-6"
              >
                {related.map((l) => (
                  <Link
                    key={l.to}
                    to={l.to}
                    className="text-[0.9rem] font-medium text-ink-secondary underline underline-offset-4 transition-colors hover:text-forest-mid"
                  >
                    {l.label}
                  </Link>
                ))}
              </nav>
            ) : null}
          </div>
        </div>
      </div>
    </main>
  );
}

export default DocLayout;

