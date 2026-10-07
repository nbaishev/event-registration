import { Alert, Button, Paper, Stack, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { ApiError } from '../../api/client';
import { eventKeys, getEventStats } from './api';

function errorMessage(error: unknown): string {
  const code = error instanceof ApiError ? error.code : '';
  const messages: Record<string, string> = {
    EVENT_NOT_OWNER: 'Нет доступа к статистике этого мероприятия.',
    EVENT_NOT_FOUND: 'Мероприятие не найдено.',
    EVENT_NOT_PUBLISHED: 'Статистика доступна после публикации мероприятия.',
    AUTH_REQUIRED: 'Войдите в аккаунт организатора, чтобы увидеть статистику.',
  };
  return messages[code] ?? 'Не удалось загрузить статистику. Повторите попытку.';
}

export function EventStats({ ownerId, eventId }: { ownerId: string; eventId: string }) {
  const query = useQuery({
    queryKey: eventKeys.stats(ownerId, eventId),
    queryFn: ({ signal }) => getEventStats(eventId, signal),
    retry: false,
    refetchOnWindowFocus: false,
  });
  const metrics = query.data ? [
    ['Вместимость', query.data.capacity],
    ['Подтверждено', query.data.confirmed],
    ['В листе ожидания', query.data.waitlist],
    ['Отмечено на входе', query.data.checked_in],
    ['Свободных мест', query.data.available_slots],
  ] as const : [];
  return <Stack component="section" aria-label="Статистика мероприятия" spacing={2}>
    <Typography component="h2" variant="h6">Статистика мероприятия</Typography>
    {query.isPending && <Typography role="status">Загружаем статистику…</Typography>}
    {query.isError && <Stack spacing={1}>
      <Alert severity="error">{errorMessage(query.error)}</Alert>
      <Button disabled={query.isFetching} onClick={() => { void query.refetch(); }}>Повторить</Button>
    </Stack>}
    {!query.isPending && !query.isError && <Stack direction="row" useFlexGap flexWrap="wrap" spacing={2}>
      {metrics.map(([label, value]) => <Paper key={label} role="group" aria-label={label} variant="outlined" sx={{ p: 2, flex: '1 1 130px' }}>
        <Typography color="text.secondary" variant="body2">{label}</Typography>
        <Typography variant="h4" component="p">{value}</Typography>
      </Paper>)}
    </Stack>}
    <Button onClick={() => { void query.refetch(); }} disabled={query.isFetching}>Обновить статистику</Button>
  </Stack>;
}
