import { expect, test } from '@playwright/test';

test('login limiter permits initial request plus burst five and ignores forged forwarded IPs', async ({ request, baseURL }) => {
  // The verification runner restarts this isolated project's Nginx immediately before this probe.
  const csrf = await request.get('/api/auth/csrf');
  const token = (await csrf.json()).csrf_token;
  const responses = await Promise.all(Array.from({ length: 20 }, (_, index) => request.post('/api/auth/login', {
    data: { email: 'unknown@example.com', password: 'incorrect password' },
    headers: { Origin: baseURL!, 'X-CSRF-Token': token, 'X-Forwarded-For': `192.0.2.${index + 1}` },
  })));
  expect(responses.filter(response => response.status() === 401)).toHaveLength(6);
  expect(responses.filter(response => response.status() === 429)).toHaveLength(14);
  for (const response of responses.filter(response => response.status() === 429)) {
    expect(await response.json()).toEqual({ error: { code: 'AUTH_RATE_LIMITED', message: 'Too many login attempts.', details: {} } });
    expect(response.headers()['cache-control']).toBe('no-store');
  }
  const unlimited = await Promise.all(Array.from({ length: 20 }, () => request.get('/api/auth/csrf')));
  expect(unlimited.every(response => response.status() === 200)).toBe(true);
  // Logout remains available even when the login bucket is exhausted.
  const guard = (await request.get('/api/auth/csrf').then(response => response.json())).csrf_token;
  const logout = await request.post('/api/auth/logout', { headers: { Origin: baseURL!, 'X-CSRF-Token': guard } });
  expect(logout.status()).toBe(204);
});
