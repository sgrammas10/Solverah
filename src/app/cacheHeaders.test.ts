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
 * Three properties hold the line:
 *   1. the long cache is scoped to `/assets/`, and nothing else;
 *   2. every file Vite emits into `/assets/` carries a content hash, so being
 *      under that prefix is the same claim as being immutable;
 *   3. a path under `/assets/` that the build did *not* emit 404s, rather than
 *      falling through the SPA catch-all and being answered with the HTML
 *      shell — which the immutable header would then pin for a year.
 *
 * (2) is asserted against `vite.config.ts` rather than against a build, so it
 * fails at the moment someone configures an unhashed output name. (3) is a
 * property of the rewrite list rather than of the headers, so it is asserted
 * there; measured against production before the passthrough rule existed,
 * `GET /assets/entry-DEADBEEF.js` returned `200 text/html`.
 */

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

const REPO_ROOT = resolve(__dirname, '..', '..');

interface VercelHeaderRule {
  source: string;
  headers: { key: string; value: string }[];
}

interface VercelRewriteRule {
  source: string;
  destination: string;
}

interface VercelConfig {
  rewrites: VercelRewriteRule[];
  headers: VercelHeaderRule[];
}

function vercelConfig(): VercelConfig {
  const raw = readFileSync(resolve(REPO_ROOT, 'vercel.json'), 'utf8');
  return JSON.parse(raw) as VercelConfig;
}

function cacheControlRules(): VercelHeaderRule[] {
  return vercelConfig().headers.filter((rule) =>
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
    // The immutable header's safety rests on this: a file under /assets/ with
    // no content hash would be cached for a year under a name the next deploy
    // reuses.
    //
    // Only a quoted string literal can be checked for '[hash]' by reading the
    // file. A template literal, a function, or a variable is not statically
    // verifiable, and those FAIL rather than pass — a guard that goes quiet
    // the moment the config gets clever is not a guard. Keys left unconfigured
    // fall back to Vite's own hashed defaults and so have nothing to report.
    const config = readFileSync(resolve(REPO_ROOT, 'vite.config.ts'), 'utf8');

    const unhashed: string[] = [];
    const unverifiable: string[] = [];

    for (const match of config.matchAll(/(entry|chunk|asset)FileNames\s*:/g)) {
      const key = `${match[1]}FileNames`;
      const rest = config.slice(match.index! + match[0].length);
      // Both quote styles; the backreference stops the other one from closing
      // the literal early.
      const literal = /^[ \t]*(['"])((?:(?!\1).)*)\1/.exec(rest);

      if (literal === null) {
        unverifiable.push(`${key}:${rest.split('\n')[0]}`);
      } else if (!literal[2].includes('[hash]')) {
        unhashed.push(`${key}: ${literal[2]}`);
      }
    }

    expect(unhashed, 'output name under /assets/ carries no content hash').toEqual([]);
    expect(
      unverifiable,
      'value is not a string literal, so [hash] cannot be checked by reading vite.config.ts',
    ).toEqual([]);
  });
});

describe('vercel.json rewrites', () => {
  // This asserts the OUTCOME -- no SPA rewrite may match a path under
  // /assets/ -- rather than any particular way of achieving it, because the
  // first attempt at achieving it did not work and passed a test anyway.
  //
  // What was tried: an identity rewrite `/assets/(.*)` -> `/assets/$1` placed
  // ahead of the catch-all, on the theory that matching it first would leave
  // the request an ordinary static lookup that misses and 404s. Measured in
  // production after deploying exactly that:
  //   GET /assets/entry-DEADBEEF.js -> 200, text/html,
  //                                    cache-control: max-age=31536000, immutable
  // Vercel checks the filesystem BEFORE rewrites, so a real asset never
  // reaches this list at all -- and a missing one, having missed the
  // filesystem twice, keeps falling through to the catch-all. The identity
  // rule cannot stop a fallthrough; only not matching can. Hence the negative
  // lookahead on the catch-all itself.
  //
  // The immutable header above is safe *because* of this property, so a
  // regression has to fail here rather than quietly pin the HTML shell at a
  // hashed URL for a year -- which no redeploy can reach, because the browser
  // never asks again.
  const MISSING_ASSET = '/assets/entry-DEADBEEF.js';

  it('has no SPA rewrite that can answer a missing /assets/ path', () => {
    const spaRewrites = vercelConfig().rewrites.filter(
      (r) => r.destination === '/index.html'
    );

    // At least one must exist or client-side routing is broken entirely.
    expect(spaRewrites.length).toBeGreaterThan(0);

    for (const rule of spaRewrites) {
      const pattern = new RegExp(`^${rule.source}$`);
      expect(
        pattern.test(MISSING_ASSET),
        `rewrite ${rule.source} -> /index.html answers ${MISSING_ASSET}, which the ` +
          `immutable header would then cache for a year`
      ).toBe(false);
    }
  });

  it('still routes ordinary SPA paths to index.html', () => {
    // The exclusion must be surgical: narrowing it until deep links break is
    // the obvious way to make the test above pass for the wrong reason.
    const spaRewrites = vercelConfig().rewrites.filter(
      (r) => r.destination === '/index.html'
    );
    const matches = (path: string) =>
      spaRewrites.some((rule) => new RegExp(`^${rule.source}$`).test(path));

    for (const path of ['/', '/login', '/job-seeker/dashboard', '/companies/1']) {
      expect(matches(path), `${path} must still reach the SPA shell`).toBe(true);
    }
  });
});
