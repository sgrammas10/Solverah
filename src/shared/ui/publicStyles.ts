/**
 * Class strings shared by the public pages (landing, legal, transparency, quiz
 * previews) so they read as one site. They are the landing page's own values:
 * the landing sets the visual language and the other public pages follow it.
 *
 * Plain strings, not components, so importing them costs nothing on the eager
 * path and Tailwind still sees every class literally.
 */

export const CONTAINER = "mx-auto w-full max-w-[1180px] px-6";

export const PRIMARY =
  "inline-flex items-center justify-center rounded-[4px] bg-forest-dark px-7 py-3.5 font-headline text-[0.98rem] font-bold text-white transition-colors hover:bg-forest-mid";

export const SECONDARY =
  "inline-flex items-center justify-center rounded-[4px] border-2 border-forest-dark px-6 py-3 text-[0.95rem] font-semibold text-forest-dark transition-colors hover:bg-forest-pale";

/** Page title on the inner public pages; the same size as the landing's section headings. */
export const PAGE_H1 =
  "font-headline text-[clamp(2rem,4.2vw,3.1rem)] font-extrabold leading-[1.02] tracking-[-0.02em] text-balance";

/** Lead paragraph under a page title. */
export const LEAD = "text-[1.02rem] leading-[1.6] text-ink-secondary";

/** Section heading in a DocLayout article. Carries the anchor the contents link to. */
export const DOC_H2 =
  "scroll-mt-24 font-headline text-[1.45rem] font-bold leading-tight tracking-[-0.01em] text-ink-primary";

/** Body paragraph in a DocLayout article: larger than UI text, set for reading. */
export const DOC_P = "text-[1.05rem] leading-[1.7] text-ink-primary";
