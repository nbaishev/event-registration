import { Alert, Button, Stack, Typography } from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router';
import { ApiError, getAuthPhase } from '../../api/client';
import { useSession } from '../auth/session';
import type { PublicEventResponse } from '../events/api';
import { cancelRegistration, getMyRegistration, registerForEvent, registrationKeys } from './api';

export function EventRegistrationPanel({ event }: { event: PublicEventResponse }) {
  const session = useSession();
  const user = session.data;
  const client = useQueryClient();
  const key = registrationKeys.detail(user?.id ?? '', event.id);
  const own = useQuery({ queryKey: key, queryFn: ({ signal }) => getMyRegistration(event.id, signal), enabled: !!user, retry: false });
  const mutation = useMutation({
    mutationFn: () => registerForEvent(event.id), retry: false,
    onSuccess: async response => {
      await client.cancelQueries({ queryKey: key, exact: true });
      client.setQueryData(key, response);
    },
    onError: async cause => {
      if (cause instanceof ApiError && cause.code === 'ALREADY_REGISTERED') await own.refetch();
    },
  });
  const cancellation = useMutation({
    mutationFn: () => cancelRegistration(event.id), retry: false,
    onSuccess: async response => {
      await client.cancelQueries({ queryKey: key, exact: true });
      client.setQueryData(key, response);
      mutation.reset();
    },
    onError: async cause => {
      if (cause instanceof ApiError && cause.code === 'REGISTRATION_NOT_FOUND') await own.refetch();
    },
  });
  const cancelMessages: Record<string, string> = {
    TICKET_ALREADY_CHECKED_IN: 'Билет уже использован',
    EVENT_ALREADY_STARTED: 'Мероприятие уже началось',
    EVENT_FINISHED: 'Мероприятие завершилось',
    EVENT_CANCELLED: 'Мероприятие отменено',
  };
  const cancelAction = <>
    {cancellation.isError && <Alert severity="error">{cancellation.error instanceof ApiError && cancelMessages[cancellation.error.code] || 'Не удалось отменить регистрацию. Проверьте текущий статус перед повторной попыткой.'}</Alert>}
    {event.status === 'PUBLISHED' && Date.now() < Date.parse(event.starts_at) && <Button disabled={cancellation.isPending} onClick={() => cancellation.mutate()}>{cancellation.isPending ? 'Отменяем…' : 'Отменить регистрацию'}</Button>}
    <Button disabled={cancellation.isPending} onClick={() => { void own.refetch(); }}>Проверить текущий статус</Button>
  </>;
  if (session.isError) return <Stack spacing={1}><Alert severity="error">Не удалось проверить вход</Alert><Button onClick={() => { void session.refetch(); }}>Повторить проверку входа</Button></Stack>;
  if (!user) {
    if (session.isPending && getAuthPhase() === 'active') return <Typography role="status">Проверяем вход…</Typography>;
    return <Button component={Link} to="/login">Войти для регистрации</Button>;
  }
  if (own.isPending) return <Typography role="status">Загружаем регистрацию…</Typography>;
  if (own.isError) return <Stack spacing={1}><Alert severity="error">Не удалось загрузить регистрацию</Alert><Button onClick={() => { void own.refetch(); }}>Повторить загрузку регистрации</Button></Stack>;
  const registration = own.data;
  if (registration?.status === 'CONFIRMED') return <Stack spacing={1}><Typography>Регистрация подтверждена</Typography><Typography>Билет</Typography><Typography sx={{ fontFamily: 'monospace' }}>{registration.ticket_code}</Typography>{cancelAction}</Stack>;
  if (registration?.status === 'WAITLIST') return <Stack spacing={1}><Typography>Вы в списке ожидания</Typography><Typography>Место в очереди: {registration.waitlist_position}</Typography>{cancelAction}</Stack>;
  if (event.status !== 'PUBLISHED' || Date.now() >= Date.parse(event.starts_at)) return <Typography>Регистрация закрыта</Typography>;
  return <Stack spacing={1}>
    {registration?.status === 'CANCELLED' && <Typography>Регистрация отменена</Typography>}
    {mutation.isError && <Alert severity="error">{mutation.error instanceof ApiError && mutation.error.code === 'OWNER_CANNOT_REGISTER' ? 'Организатор не может зарегистрироваться на своё мероприятие' : 'Не удалось зарегистрироваться. Проверьте текущий статус перед повторной попыткой.'}</Alert>}
    <Button variant="contained" disabled={mutation.isPending} onClick={() => { cancellation.reset(); mutation.mutate(); }}>{mutation.isPending ? 'Регистрируем…' : 'Зарегистрироваться'}</Button>
    {mutation.isError && <Button onClick={() => { void own.refetch(); }}>Проверить текущий статус</Button>}
  </Stack>;
}
