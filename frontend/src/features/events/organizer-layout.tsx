import { Alert, Button, Container, Link, Stack, Typography } from '@mui/material';
import { Link as RouterLink, Navigate, Outlet } from 'react-router';
import { getAuthPhase } from '../../api/client';
import { useSession } from '../auth/session';
export function OrganizerLayout() {
  const session = useSession();
  if (getAuthPhase() === 'anonymous') return <Navigate to="/login" replace />;
  if (session.isPending) return <Typography role="status" sx={{ p: 4 }}>Проверяем сессию…</Typography>;
  if (session.isError) return <Container sx={{ py: 4 }}><Stack spacing={2}><Alert severity="error">Не удалось проверить сессию</Alert><Button onClick={() => { void session.refetch(); }}>Повторить</Button></Stack></Container>;
  if (!session.data) return <Navigate to="/login" replace />;
  return <Container maxWidth="md" sx={{ py: 4 }}>
    <Stack component="nav" direction="row" spacing={3} sx={{ mb: 4 }}>
      <Link component={RouterLink} to="/">Мой аккаунт</Link>
      <Link component={RouterLink} to="/organizer/events">Мои мероприятия</Link>
    </Stack>
    <Outlet context={session.data.id} />
  </Container>;
}
