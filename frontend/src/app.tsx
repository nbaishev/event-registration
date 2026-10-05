import { CssBaseline } from '@mui/material';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState } from 'react';
import { BrowserRouter, Route, Routes } from 'react-router';
import { AccountPage } from './features/auth/account-page';
import { LoginPage } from './features/auth/login-page';
import { SessionBoundary } from './features/auth/session';
import { RegisterPage } from './features/auth/register-page';

export function App({ client }: { client?: QueryClient } = {}) {
  const [queryClient] = useState(() => client ?? new QueryClient());
  return (
    <QueryClientProvider client={queryClient}>
      <CssBaseline />
      <BrowserRouter>
        <SessionBoundary />
        <Routes>
          <Route path="/" element={<AccountPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
