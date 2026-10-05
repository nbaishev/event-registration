import { Alert, Button, Container, Paper, Stack, Typography } from '@mui/material';
import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Navigate, useNavigate } from 'react-router';
import { ApiError, apiRequest } from '../../api/client';
import { useSession } from './session';

export function AccountPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [pending, setPending] = useState(false);
  const session = useSession(!pending);
  const [error, setError] = useState<string>();
  async function logout() {
    if (pending) return;
    setPending(true);
    setError(undefined);
    try {
      await apiRequest<void>('/api/auth/logout', { method: 'POST' });
      await queryClient.cancelQueries();
      queryClient.clear();
      navigate('/login', { replace: true });
    } catch (cause) {
      setError(cause instanceof ApiError && cause.code === 'CSRF_INVALID'
        ? 'Защита запроса обновлена. Повторите попытку'
        : 'Не удалось выйти. Повторите попытку');
      setPending(false);
    }
  }
  if (session.isPending) return <Typography role="status" sx={{ p: 4 }}>Проверяем сессию…</Typography>;
  if (session.isError) return (
    <Container maxWidth="sm" sx={{ py: 8 }}><Stack spacing={2}>
      <Alert severity="error">Не удалось проверить сессию</Alert>
      <Button onClick={() => { void session.refetch(); }}>Повторить</Button>
    </Stack></Container>
  );
  if (!session.data) return <Navigate to="/login" replace />;
  return (
    <Container maxWidth="sm" sx={{ py: 8 }}>
      <Paper variant="outlined" sx={{ p: 4 }}><Stack spacing={3}>
        <Typography component="h1" variant="h4">Мой аккаунт</Typography>
        <Typography>{session.data.email}</Typography>
        {error && <Alert severity="error">{error}</Alert>}
        <Button variant="contained" disabled={pending} onClick={() => { void logout(); }}>{pending ? 'Выходим…' : 'Выйти'}</Button>
      </Stack></Paper>
    </Container>
  );
}
