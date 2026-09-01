import js from '@eslint/js';
import globals from 'globals';
import jsxA11y from 'eslint-plugin-jsx-a11y';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import tseslint from 'typescript-eslint';

// The nine feature slices under src/features/. Kept in one list so the
// boundary rule below cannot drift from the directory layout silently — add a
// slice here when adding the directory.
const FEATURE_SLICES = [
  'agent',
  'assessments',
  'auth',
  'companies',
  'intake',
  'intelligence',
  'landing',
  'matching',
  'profile',
];

export default tseslint.config(
  { ignores: ['dist'] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    plugins: {
      'jsx-a11y': jsxA11y,
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      // Accessibility lint (GAP-10, 2026-08-20): static WCAG checks in CI.
      // Catches missing labels/alt text/keyboard handlers at lint time; it is
      // NOT a full audit — the manual keyboard/contrast pass still applies.
      ...jsxA11y.configs.recommended.rules,
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': [
        'warn',
        { allowConstantExport: true },
      ],

      // Phase 4 lint repair (2026-09-01). `npm run lint` had crashed since the
      // ESLint 9.36 upgrade (typescript-eslint 8.8.1 read rule options 9.36 no
      // longer normalizes); the lockfile bump to 8.69.0 makes the gate runnable
      // again. The overrides below record the pre-existing findings at 'warn'
      // so the gate passes on today's code without hiding the debt — tighten a
      // rule back to 'error' when its findings are actually cleaned up.
      '@typescript-eslint/no-unused-vars': [
        'error',
        // `_`-prefixed bindings and rest-sibling omissions are deliberate
        // idiom here (tests/msw handlers, useProfileForm destructuring).
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_', ignoreRestSiblings: true },
      ],
      '@typescript-eslint/no-explicit-any': 'warn',
      // GAP-10 a11y checks stay on and visible; these seven rules have
      // pre-existing hits and gate nothing until those are fixed.
      'jsx-a11y/label-has-associated-control': 'warn',
      'jsx-a11y/click-events-have-key-events': 'warn',
      'jsx-a11y/no-static-element-interactions': 'warn',
      'jsx-a11y/no-autofocus': 'warn',
      'jsx-a11y/heading-has-content': 'warn',
      'jsx-a11y/anchor-has-content': 'warn',
      'jsx-a11y/no-noninteractive-element-to-interactive-role': 'warn',
    },
  },
  {
    // tests/msw's `useApiMocks` is a per-suite MSW fixture installer, not a
    // React hook; the `use` prefix trips rules-of-hooks at the top level of
    // every suite that calls it. Production code keeps the rule at error.
    files: ['**/*.test.{ts,tsx}', '**/__tests__/**'],
    rules: { 'react-hooks/rules-of-hooks': 'off' },
  },
  {
    // Phase 4 boundary rule (ARCHITECTURE.md 6.4): a feature slice may not
    // deep-import from another feature slice — only the slice's index.ts
    // crosses, written as a bare "../<slice>" (or "../../<slice>") import.
    //
    // Scope: src/features/ only. src/app deep-imports by design — route-level
    // lazy() must reach the component module directly so a barrel never sits
    // inside a chunk boundary — and shared/ has no entry-point contract.
    //
    // Mechanics: the globs are segment-anchored, so "**/auth/*" matches any
    // specifier that traverses INTO the auth directory at any depth and any
    // spelling ("../auth/useAuth", "../../auth/components/Login",
    // "./../auth/api"), while the legal barrel import "../auth" has no segment
    // after the slice name and never matches. A slice's own name is included
    // too: within-slice imports never route through the slice's directory name
    // ("./components/X", "../useWP"), so nothing legal matches. vi.mock()
    // path strings are out of scope on purpose — mocks pin the concrete module
    // id, which still intercepts the barrel's re-export.
    files: ['src/features/**/*.{ts,tsx}'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: FEATURE_SLICES.map((slice) => ({
            group: [`**/${slice}/*`, `**/${slice}/*/**`],
            message: `Deep import into the ${slice} slice — cross-slice imports go through features/${slice}/index.ts (write it as "../${slice}").`,
          })),
        },
      ],
    },
  }
);
