import { Alert, Button, Link, Paper, Stack, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { Link as RouterLink, useOutletContext } from 'react-router';
import { eventKeys, getMyEvents } from './api';
import { formatEventTime } from './event-time';
export function EventListPage() {
  const ownerId = useOutletContext<string>();
  const query = useQuery({ queryKey: eventKeys.mine(ownerId), queryFn: ({ signal }) => getMyEvents(signal), retry: false });
  return <Stack spacing={3}>
    <Typography component="h1" variant="h4">Мои мероприятия</Typography>
    <Button component={RouterLink} to="/organizer/events/new" variant="contained">Создать мероприятие</Button>
    {query.isPending && <Typography role="status">Загружаем мероприятия…</Typography>}
    {query.isError && <><Alert severity="error">Не удалось загрузить мероприятия</Alert><Button onClick={() => { void query.refetch(); }}>Повторить</Button></>}
    {query.data?.length === 0 && <Typography>У вас пока нет мероприятий</Typography>}
    {query.data?.map(event => <Paper key={event.id} variant="outlined" sx={{ p: 3 }}><Stack spacing={1}>
      <Link component={RouterLink} to={`/organizer/events/${event.id}`}>{event.title}</Link>
      <Typography>{formatEventTime(event.starts_at, event.timezone)} · {event.timezone}</Typography>
      <Typography>{event.status === 'DRAFT' ? 'Черновик' : event.status === 'CANCELLED' ? 'Отменено' : 'Опубликовано'} · Мест: {event.capacity}</Typography>
    </Stack></Paper>)}
  </Stack>;
}
