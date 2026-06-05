import { defineConfig } from 'vitest/config';
import { resolve } from 'node:path';

export default defineConfig({
  test: {
    environment: 'node',
    include: [
      'services/**/__tests__/**/*.test.ts',
      'lib/**/__tests__/**/*.test.ts',
      'entrypoints/**/__tests__/**/*.test.ts',
      'tests/**/*.test.ts',
    ],
  },
  resolve: {
    alias: {
      '@': resolve(__dirname, '.'),
    },
  },
});
