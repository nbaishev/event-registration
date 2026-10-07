import { Alert, Button, Container, Link, Paper, Stack, Typography } from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink, Navigate } from 'react-router';
import { ApiError, getAuthPhase } from '../../api/client';
import { useSession } from '../auth/session';
import { formatEventTime } from '../events/event-time';
import { applyRegistrationMutation, cancelRegistration, getMyRegistrations, registrationKeys, type MyRegistrationResponse } from './api';

function RegistrationItem({ item, userId }: { item: MyRegistrationResponse; userId: string }) {
  const client = useQueryClient();
  const { event, registration } = item;
  const cancellation = useMutation({
    mutationFn: () => cancelRegistration(event.id), retry: false,
    onSuccess: saved => applyRegistrationMutation(client, userId, saved),
    onError: async cause => {
      if (cause instanceof ApiError && cause.code === 'REGISTRATION_NOT_FOUND') await client.invalidateQueries({ queryKey: registrationKeys.mine(userId), exact: true });
    },
  });
  const messages: Record<string, string> = {
    TICKET_ALREADY_CHECKED_IN: 'Билет уже использован', EVENT_ALREADY_STARTED: 'Мероприятие уже началось',
    EVENT_FINISHED: 'Мероприятие завершилось', EVENT_CANCELLED: 'Мероприятие отменено',
  };
  return <Paper component="article" variant="outlined" sx={{ p: 3 }}><Stack spacing={1}>
    <Link component={RouterLink} to={`/events/${encodeURIComponent(event.slug)}`} variant="h6">{event.title}</Link>
    <Typography>Начало: {formatEventTime(event.starts_at, event.timezone)}</Typography>
    <Typography>Окончание: {formatEventTime(event.ends_at, event.timezone)} · {event.timezone}</Typography>
    {event.status === 'FINISHED' && <Typography>Мероприятие завершилось</Typography>}
    {event.status === 'CANCELLED' && <Typography>Мероприятие отменено</Typography>}
    {registration.status === 'CONFIRMED' && <><Typography>Регистрация подтверждена</Typography><Typography>Билет</Typography><Typography sx={{ fontFamily: 'monospace' }}>{registration.ticket_code}</Typography></>}
    {registration.status === 'WAITLIST' && <><Typography>Вы в списке ожидания</Typography><Typography>Место в очереди: {registration.waitlist_position}</Typography></>}
    {registration.status === 'CANCELLED' && <Typography>Регистрация отменена</Typography>}
    {cancellation.isError && <Alert severity="error">{cancellation.error instanceof ApiError && messages[cancellation.error.code] || 'Не удалось отменить регистрацию. Проверьте текущий статус перед повторной попыткой.'}</Alert>}
    {registration.status !== 'CANCELLED' && event.status === 'PUBLISHED' && Date.now() < Date.parse(event.starts_at) && <Button disabled={cancellation.isPending} onClick={() => cancellation.mutate()}>{cancellation.isPending ? 'Отменяем…' : 'Отменить регистрацию'}</Button>}
  </Stack></Paper>;
}

export function MyRegistrationsPage() {
  const session = useSession();
  const user = session.data;
  const list = useQuery({ queryKey: registrationKeys.mine(user?.id ?? ''), queryFn: ({ signal }) => getMyRegistrations(signal), enabled: !!user && getAuthPhase() === 'active', retry: false });
  if (getAuthPhase() === 'anonymous') return <Navigate to="/login" replace />;
  if (session.isPending) return <Typography role="status" sx={{ p: 4 }}>Проверяем сессию…</Typography>;
  if (session.isError) return <Container sx={{ py: 4 }}><Alert severity="error">Не удалось проверить сессию</Alert><Button onClick={() => { void session.refetch(); }}>Повторить</Button></Container>;
  if (!user) return <Navigate to="/login" replace />;
  return <Container maxWidth="md" sx={{ py: 4 }}><Stack spacing={3}>
    <Link component={RouterLink} to="/">Мой аккаунт</Link>
    <Typography component="h1" variant="h4">Мои регистрации</Typography>
    {list.isPending ? <Typography role="status">Загружаем регистрации…</Typography> : list.isError ? <Alert severity="error">Не удалось загрузить регистрации</Alert> : list.data.length === 0 ? <Typography>У вас пока нет регистраций</Typography> : list.data.map(item => <RegistrationItem key={`${user.id}:${item.registration.id}`} item={item} userId={user.id} />)}
    <Button disabled={list.isFetching} onClick={() => { void list.refetch(); }}>{list.isError ? 'Повторить' : 'Проверить текущий статус'}</Button>
  </Stack></Container>;
}
