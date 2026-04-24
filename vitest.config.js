import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'happy-dom',
    setupFiles: ['./tests/vault/setup.js'],
    include: ['tests/vault/**/*.test.js'],
    hookTimeout: 60_000,
    testTimeout: 120_000,
  },
});
