/**
 * Cache-Control policy — a long cache must never reach a non-hashed path.
 *
 * Before this, Vercel served everything with `public, max-age=0,
 * must-revalidate`: correct for `index.html`, but it also means every hashed
 * build asset is re-validated on every visit despite its filename already
 * guaranteeing the content can never change.
 *
 * The fix is one narrow override, and the danger is entirely in its scope. A
 * `max-age=31536000, immutable` header on `index.html` — or on any path a
 * future build might emit without a content hash — pins returning visitors to
 * a stale shell for a year. There is no way to un-ship that: the browser will
 * not ask again, so no redeploy reaches those users. It is the one mistake in
 * this change that cannot be rolled back, which is why it is tested rather
 * than reviewed.
 *
 * Two properties hold the line:
 *   1. the long cache is scoped to `/assets/`, and nothing else;
 *   2. every file Vite emits into `/assets/` carries a content hash, so being
 *      under that prefix is the same claim as being immutable.
 *
 * (2) is asserted against `vite.config.ts` rather than against a build, so it
 * fails at the moment someone configures an unhashed output name.
 */

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

const REPO_ROOT = resolve(__dirname, '..', '..');

interface VercelHeaderRule {
  source: string;
  headers: { key: string; value: string }[];
}

function headerRules(): VercelHeaderRule[] {
  const raw = readFileSync(resolve(REPO_ROOT, 'vercel.json'), 'utf8');
  return (JSON.parse(raw) as { headers: VercelHeaderRule[] }).headers;
}

function cacheControlRules(): VercelHeaderRule[] {
  return headerRules().filter((rule) =>
    rule.headers.some((h) => h.key.toLowerCase() === 'cache-control'),
  );
}

function cacheControlValue(rule: VercelHeaderRule): string {
  return rule.headers.find((h) => h.key.toLowerCase() === 'cache-control')!.value;
}

describe('vercel.json cache policy', () => {
  it('scopes every long-lived cache to /assets/', () => {
    const longLived = cacheControlRules().filter((rule) => {
      const maxAge = /max-age=(\d+)/.exec(cacheControlValue(rule));
      return maxAge !== null && Number(maxAge[1]) > 0;
    });

    expect(longLived.length).toBeGreaterThan(0);
    for (const rule of longLived) {
      // Anything broader than this prefix can match index.html.
      expect(rule.source).toBe('/assets/(.*)');
    }
  });

  it('marks the /assets/ cache immutable', () => {
    const assets = cacheControlRules().find((r) => r.source === '/assets/(.*)');

    expect(assets).toBeDefined();
    expect(cacheControlValue(assets!)).toBe('public, max-age=31536000, immutable');
  });

  it('makes everything else revalidate on every request', () => {
    const blanket = cacheControlRules().find((r) => r.source === '/(.*)');

    expect(blanket).toBeDefined();
    // max-age=0 + must-revalidate is no-cache semantics: the browser may hold
    // the bytes but must ask before reusing them, so a deploy is visible on
    // the next request instead of whenever a TTL happens to lapse.
    expect(cacheControlValue(blanket!)).toBe('public, max-age=0, must-revalidate');
  });

  it('applies the /assets/ override after the blanket rule', () => {
    // Vercel applies every matching rule in order and the last one wins for a
    // given header key. Reversed, the blanket no-cache would win and assets
    // would simply stop being cached — today's behaviour, and harmless. This
    // asserts the intended order anyway so the ordering stays deliberate.
    const sources = cacheControlRules().map((r) => r.source);

    expect(sources.indexOf('/(.*)')).toBeLessThan(sources.indexOf('/assets/(.*)'));
  });

  it('emits no unhashed filename into /assets/', () => {
    // The immutable header's safety rests entirely on this: a file under
    // /assets/ without a content hash would be cached for a year under a name
    // the next deploy reuses.
    const config = readFileSync(resolve(REPO_ROOT, 'vite.config.ts'), 'utf8');

    for (const [, name] of config.matchAll(
      /(?:entry|chunk|asset)FileNames:\s*'([^']+)'/g,
    )) {
      expect(name).toContain('[hash]');
    }
  });
});
