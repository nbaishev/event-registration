import { Alert, Button, Container, Paper, Stack, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router';
import { ApiError } from '../../api/client';
import { getPublicEvent, publicEventKey } from './api';
import { formatEventTime } from './event-time';

export function PublicEventPage() {
  const { slug = '' } = useParams();
  const query = useQuery({ queryKey: publicEventKey(slug), queryFn: ({ signal }) => getPublicEvent(slug, signal), retry: false });
  if (query.isPending) return <Container sx={{ py: 4 }}><Typography role="status">Загружаем мероприятие…</Typography></Container>;
  if (query.isError) {
    const missing = query.error instanceof ApiError && query.error.code === 'EVENT_NOT_FOUND';
    return <Container sx={{ py: 4 }}><Stack spacing={2}><Alert severity="error">{missing ? 'Мероприятие не найдено' : 'Не удалось загрузить мероприятие'}</Alert><Button onClick={() => { void query.refetch(); }}>Повторить</Button></Stack></Container>;
  }
  const event = query.data;
  return <Container maxWidth="md" sx={{ py: 4 }}><Paper variant="outlined" sx={{ p: 4 }}><Stack spacing={3}>
    <Typography component="h1" variant="h4">{event.title}</Typography>
    <Typography>{event.status === 'FINISHED' ? 'Завершено' : event.status === 'CANCELLED' ? 'Отменено' : 'Опубликовано'}</Typography>
    <Typography sx={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{event.description}</Typography>
    <Typography>Начало: {formatEventTime(event.starts_at, event.timezone)}</Typography>
    <Typography>Окончание: {formatEventTime(event.ends_at, event.timezone)}</Typography>
    <Typography>Часовой пояс: {event.timezone}</Typography>
    <Typography>Количество мест: {event.capacity}</Typography>
  </Stack></Paper></Container>;
}
