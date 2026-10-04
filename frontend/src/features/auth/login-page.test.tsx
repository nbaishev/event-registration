import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { App } from '../../app';

afterEach(() => vi.unstubAllGlobals());
it('shows server field validation safely and allows correcting the login form', async () => {
  window.history.replaceState({}, '', '/login');
  vi.stubGlobal('fetch', vi.fn<typeof fetch>(async input => {
    if (input === '/api/auth/csrf') return new Response(JSON.stringify({ csrf_token: 'test-token' }));
    return new Response(JSON.stringify({ error: { code: 'VALIDATION_ERROR', message: 'Invalid request.', details: { fields: [{ field: 'email', code: 'INVALID_EMAIL' }, { field: 'password', code: 'PASSWORD_LENGTH' }] } } }), { status: 422 });
  }));
  render(<App />);
  fireEvent.change(screen.getByLabelText(/^Email/), { target: { value: 'invalid' } });
  fireEvent.change(screen.getByLabelText(/^Пароль/), { target: { value: 'short' } });
  fireEvent.click(screen.getByRole('button', { name: 'Войти' }));
  expect(await screen.findByText('Укажите корректный email')).toBeVisible();
  expect(screen.getByText('Пароль должен содержать от 12 до 128 символов')).toBeVisible();
  expect(screen.getByRole('button', { name: 'Войти' })).toBeEnabled();
});
it('shows a recoverable network error without navigating away', async () => {
  window.history.replaceState({}, '', '/login');
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Network unavailable')));
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: 'Войти' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Не удалось отправить запрос');
  expect(window.location.pathname).toBe('/login');
  expect(screen.getByRole('button', { name: 'Войти' })).toBeEnabled();
});
