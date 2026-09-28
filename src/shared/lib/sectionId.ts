/**
 * Anchor id for a document section, derived from its heading text so a table
 * of contents and the heading it points at always agree.
 *
 * "3. What the Service is — and is not" -> "what-the-service-is-and-is-not".
 * A leading section number is dropped so the anchor survives a renumbering.
 */
export function sectionId(heading: string): string {
  return heading
    .toLowerCase()
    .replace(/^\s*\d+[.)]\s*/, "")
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}
