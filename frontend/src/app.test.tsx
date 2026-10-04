import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { App } from './app';
describe('Foundation shell', () => {
  for (const path of ['/', '/login']) {
    it(`shows the current Foundation state at ${path}`, () => {
      window.history.replaceState({}, '', path);
      render(<App />);
      expect(screen.getByRole('heading', { name: 'Event Registration' })).toBeVisible();
      expect(screen.getByText('Auth is not implemented yet.')).toBeVisible();
    });
  }
});
