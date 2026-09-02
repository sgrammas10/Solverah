import { configDefaults, defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  optimizeDeps: {
    exclude: ['lucide-react'],
  },
  // The bundle budget (.size-limit.json) has to point at the entry chunk by
  // name, and the default 'index-[hash].js' is ambiguous: a lazy chunk built
  // from a module named index.ts lands as 'index-<other-hash>.js' in the same
  // directory, so 'assets/index-*.js' matches two files and the gate silently
  // measures the wrong thing. Naming the entry explicitly makes the glob exact.
  // Only entry chunks are affected; lazy chunks keep their source-derived names.
  build: {
    rollupOptions: {
      output: {
        entryFileNames: 'assets/entry-[hash].js',
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.ts',
    // tests/e2e/*.spec.ts are Playwright specs and match Vitest's default
    // include glob, so without this Vitest collects them, imports
    // @playwright/test outside a Playwright runner, and fails. Spread the
    // defaults rather than replacing them -- assigning a bare exclude list
    // silently drops node_modules and dist from the exclusions.
    exclude: [...configDefaults.exclude, 'tests/e2e/**'],
  },
});
