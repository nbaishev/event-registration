import { Alert, Button, Paper, Stack, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useParams, useOutletContext } from 'react-router';
import { ApiError } from '../../api/client';
import { eventKeys, getEvent } from './api';
import { formatEventTime } from './event-time';
export function EventDetailPage() {
  const ownerId = useOutletContext<string>();
  const { eventId = '' } = useParams();
  const query = useQuery({ queryKey: eventKeys.detail(ownerId, eventId), queryFn: ({ signal }) => getEvent(eventId, signal), retry: false });
  if (query.isPending) return <Typography role="status">Загружаем мероприятие…</Typography>;
  if (query.isError) {
    const code = query.error instanceof ApiError ? query.error.code : '';
    const message = code === 'EVENT_NOT_FOUND' ? 'Мероприятие не найдено' : code === 'EVENT_NOT_OWNER' ? 'Нет доступа к этому мероприятию' : 'Не удалось загрузить мероприятие';
    return <Stack spacing={2}><Alert severity="error">{message}</Alert><Button onClick={() => { void query.refetch(); }}>Повторить</Button></Stack>;
  }
  const event = query.data;
  return <Paper variant="outlined" sx={{ p: 4 }}><Stack spacing={3}>
    <Typography component="h1" variant="h4">{event.title}</Typography>
    <Typography>{event.status === 'DRAFT' ? 'Черновик' : event.status === 'CANCELLED' ? 'Отменено' : 'Опубликовано'}</Typography>
    <Typography sx={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{event.description}</Typography>
    <Typography>Начало: {formatEventTime(event.starts_at, event.timezone)}</Typography>
    <Typography>Окончание: {formatEventTime(event.ends_at, event.timezone)}</Typography>
    <Typography>Часовой пояс: {event.timezone}</Typography>
    <Typography>Количество мест: {event.capacity}</Typography>
    <Typography sx={{ overflowWrap: 'anywhere' }}>Ссылка события: {event.slug}</Typography>
  </Stack></Paper>;
}
