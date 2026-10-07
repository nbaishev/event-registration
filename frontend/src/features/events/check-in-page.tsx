import { useState, type FormEvent } from 'react';
import { Alert, Button, Paper, Stack, TextField, Typography } from '@mui/material';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useOutletContext, useParams } from 'react-router';
import { ApiError } from '../../api/client';
import { checkIn, eventKeys, getEvent } from './api';
import { formatEventTime } from './event-time';

function errorMessage(error: unknown): string {
  const code = error instanceof ApiError ? error.code : '';
  const messages: Record<string, string> = {
    TICKET_NOT_FOUND: 'Билет не найден для этого мероприятия.',
    TICKET_ALREADY_CHECKED_IN: 'Участник уже отмечен.',
    CHECKIN_NOT_OPEN: 'Check-in ещё не открыт.',
    EVENT_CANCELLED: 'Мероприятие отменено.',
    EVENT_FINISHED: 'Мероприятие завершилось.',
    EVENT_NOT_OWNER: 'Нет доступа к этому мероприятию.',
    EVENT_NOT_FOUND: 'Мероприятие не найдено.',
    VALIDATION_ERROR: 'Проверьте код билета: нужны 12 символов, пробелы и дефисы допустимы.',
    AUTH_REQUIRED: 'Войдите в аккаунт организатора.',
  };
  return messages[code] ?? 'Не удалось отметить участника. Проверьте соединение; результат предыдущего запроса мог сохраниться.';
}

export function CheckInPage() {
  const ownerId = useOutletContext<string>();
  const { eventId = '' } = useParams();
  const [ticketCode, setTicketCode] = useState('');
  const query = useQuery({ queryKey: eventKeys.detail(ownerId, eventId), queryFn: ({ signal }) => getEvent(eventId, signal), retry: false });
  const mutation = useMutation({ mutationFn: (code: string) => checkIn(eventId, code), retry: false });
  function submit(event: FormEvent) {
    event.preventDefault();
    if (mutation.isPending || !ticketCode.trim()) return;
    mutation.reset();
    mutation.mutate(ticketCode);
  }
  if (query.isPending) return <Typography role="status">Загружаем мероприятие…</Typography>;
  if (query.isError) return <Alert severity="error">{errorMessage(query.error)}</Alert>;
  const event = query.data;
  if (event.status !== 'PUBLISHED') return <Alert severity="warning">{event.status === 'DRAFT' ? 'Check-in ещё не открыт.' : 'Мероприятие отменено.'}</Alert>;
  return <Paper variant="outlined" sx={{ p: 4 }}><Stack spacing={3}>
    <Typography component="h1" variant="h4">Check-in</Typography>
    <Typography variant="h6">{event.title}</Typography>
    <Stack component="form" spacing={2} onSubmit={submit}>
      <TextField label="Код билета" value={ticketCode} onChange={e => { setTicketCode(e.target.value); mutation.reset(); }} disabled={mutation.isPending} required autoComplete="off" helperText="Например: 7K4P-9Q2M-8RTA" />
      <Button type="submit" variant="contained" disabled={mutation.isPending || !ticketCode.trim()}>{mutation.isPending ? 'Отмечаем…' : 'Отметить участника'}</Button>
    </Stack>
    {mutation.isError && <Alert severity="error">{errorMessage(mutation.error)}</Alert>}
    {mutation.isSuccess && <Stack spacing={1} role="status">
      <Typography color="success.main">Участник отмечен</Typography>
      <Typography>{mutation.data.participant.email}</Typography>
      <Typography>{mutation.data.ticket_code}</Typography>
      <Typography>Время отметки: {formatEventTime(mutation.data.checked_in_at, event.timezone)}</Typography>
    </Stack>}
  </Stack></Paper>;
}
