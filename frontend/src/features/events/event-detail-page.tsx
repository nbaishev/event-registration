import { useState } from 'react';
import { Alert, Button, Dialog, DialogActions, DialogContent, DialogContentText, DialogTitle, Paper, Stack, Typography } from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink, useNavigate, useParams, useOutletContext } from 'react-router';
import { ApiError } from '../../api/client';
import { cancelEvent, deleteEvent, eventKeys, getEvent, publicEventKey, publishEvent, type EventSummary } from './api';
import { registrationKeys } from '../registrations/api';
import { formatEventTime } from './event-time';
import { EventStats } from './event-stats';
import { EventScheduleForm } from './event-schedule-form';
import { EventCapacityForm } from './event-capacity-form';
export function EventDetailPage() {
  const ownerId = useOutletContext<string>();
  const { eventId = '' } = useParams();
  const query = useQuery({ queryKey: eventKeys.detail(ownerId, eventId), queryFn: ({ signal }) => getEvent(eventId, signal), retry: false });
  const client = useQueryClient();
  const navigate = useNavigate();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const cancellation = useMutation({
    mutationFn: () => cancelEvent(eventId),
    onSuccess: async saved => {
      const key = eventKeys.detail(saved.owner_id, saved.id);
      await client.cancelQueries({ queryKey: key, exact: true });
      client.setQueryData(key, saved);
      setConfirmCancel(false);
      void client.invalidateQueries({ queryKey: eventKeys.mine(saved.owner_id) });
      void client.invalidateQueries({ queryKey: publicEventKey(saved.slug), exact: true });
      void client.invalidateQueries({ queryKey: registrationKeys.mine(ownerId), exact: true });
      void client.invalidateQueries({ queryKey: registrationKeys.detail(ownerId, saved.id), exact: true });
    },
  });
  const deletion = useMutation({
    mutationFn: () => deleteEvent(eventId),
    onSuccess: async () => {
      const detailKey = eventKeys.detail(ownerId, eventId);
      const mineKey = eventKeys.mine(ownerId);
      await Promise.all([
        client.cancelQueries({ queryKey: detailKey, exact: true }),
        client.cancelQueries({ queryKey: mineKey, exact: true }),
      ]);
      client.removeQueries({ queryKey: detailKey, exact: true });
      client.setQueryData<EventSummary[]>(mineKey, current => current?.filter(event => event.id !== eventId));
      void client.invalidateQueries({ queryKey: mineKey, exact: true });
      navigate('/organizer/events', { replace: true });
    },
  });
  const publication = useMutation({
    mutationFn: () => publishEvent(eventId),
    onSuccess: async saved => {
      const key = eventKeys.detail(saved.owner_id, saved.id);
      await client.cancelQueries({ queryKey: key, exact: true });
      client.setQueryData(key, saved);
      void client.invalidateQueries({ queryKey: eventKeys.mine(saved.owner_id) });
    },
  });
  if (query.isPending) return <Typography role="status">Загружаем мероприятие…</Typography>;
  if (query.isError) {
    const code = query.error instanceof ApiError ? query.error.code : '';
    const message = code === 'EVENT_NOT_FOUND' ? 'Мероприятие не найдено' : code === 'EVENT_NOT_OWNER' ? 'Нет доступа к этому мероприятию' : 'Не удалось загрузить мероприятие';
    return <Stack spacing={2}><Alert severity="error">{message}</Alert><Button onClick={() => { void query.refetch(); }}>Повторить</Button></Stack>;
  }
  const event = query.data;
  return <Paper variant="outlined" sx={{ p: 4 }}><Stack spacing={3}>
    <Typography component="h1" variant="h4">{event.title}</Typography>
    {event.status === 'PUBLISHED' && <Button color="error" disabled={cancellation.isPending} onClick={() => { cancellation.reset(); setConfirmCancel(true); }}>Отменить мероприятие</Button>}
    <Dialog open={confirmCancel} onClose={() => { if (!cancellation.isPending) setConfirmCancel(false); }} aria-labelledby="cancel-event-title">
      <DialogTitle id="cancel-event-title">Отменить мероприятие?</DialogTitle>
      <DialogContent>
        <DialogContentText>Мероприятие будет отменено без возможности восстановления. Участники и список ожидания получат уведомление об отмене.</DialogContentText>
        {cancellation.isError && <Alert severity="error">{cancellation.error instanceof ApiError ? {
          EVENT_NOT_OWNER: 'Нет доступа к этому мероприятию.',
          EVENT_NOT_FOUND: 'Мероприятие не найдено.',
          EVENT_CANCELLED: 'Мероприятие уже отменено.',
          EVENT_NOT_PUBLISHED: 'Мероприятие не опубликовано.',
          EVENT_ALREADY_STARTED: 'Мероприятие уже началось. Отмена недоступна.',
          CSRF_INVALID: 'Защита запроса обновлена. Повторите попытку.',
        }[cancellation.error.code] ?? 'Не удалось отменить мероприятие. Повторите попытку.' : 'Не удалось отменить мероприятие. Повторите попытку.'}</Alert>}
      </DialogContent>
      <DialogActions>
        <Button disabled={cancellation.isPending} onClick={() => setConfirmCancel(false)}>Назад</Button>
        <Button color="error" variant="contained" disabled={cancellation.isPending} onClick={() => { if (!cancellation.isPending) cancellation.mutate(); }}>{cancellation.isPending ? 'Отменяем…' : 'Подтвердить отмену'}</Button>
      </DialogActions>
    </Dialog>
    {event.status === 'DRAFT' && <Button component={RouterLink} to={`/organizer/events/${event.id}/edit`} variant="contained">Редактировать черновик</Button>}
    {event.status === 'DRAFT' && <Button variant="contained" disabled={publication.isPending || deletion.isPending} onClick={() => publication.mutate()}>{publication.isPending ? 'Публикуем…' : 'Опубликовать'}</Button>}
    {event.status === 'DRAFT' && <Button color="error" disabled={deletion.isPending || publication.isPending} onClick={() => { deletion.reset(); setConfirmDelete(true); }}>Удалить черновик</Button>}
    <Dialog open={confirmDelete} onClose={() => { if (!deletion.isPending) setConfirmDelete(false); }} aria-labelledby="delete-draft-title">
      <DialogTitle id="delete-draft-title">Удалить черновик?</DialogTitle>
      <DialogContent>
        <DialogContentText>Черновик будет удалён без возможности восстановления. Удаление доступно только для мероприятий без регистраций.</DialogContentText>
        {deletion.isError && <Alert severity="error">{deletion.error instanceof ApiError && deletion.error.code === 'EVENT_NOT_DELETABLE' ? 'Нельзя удалить мероприятие: оно уже опубликовано или содержит регистрации.' : 'Не удалось удалить черновик. Повторите попытку.'}</Alert>}
      </DialogContent>
      <DialogActions>
        <Button disabled={deletion.isPending} onClick={() => setConfirmDelete(false)}>Отмена</Button>
        <Button color="error" variant="contained" disabled={deletion.isPending} onClick={() => deletion.mutate()}>{deletion.isPending ? 'Удаляем…' : 'Удалить'}</Button>
      </DialogActions>
    </Dialog>
    {publication.isError && <Alert severity="error">{publication.error instanceof ApiError && publication.error.code === 'EVENT_NOT_PUBLISHABLE' ? 'Нельзя опубликовать мероприятие. Проверьте его состояние и время начала.' : 'Не удалось опубликовать мероприятие. Повторите попытку.'}</Alert>}
    {event.status !== 'DRAFT' && <Button component={RouterLink} to={`/events/${event.slug}`}>Открыть публичную страницу</Button>}
    <Typography>{event.status === 'DRAFT' ? 'Черновик' : event.status === 'CANCELLED' ? 'Отменено' : 'Опубликовано'}</Typography>
    <Typography sx={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{event.description}</Typography>
    <Typography>Начало: {formatEventTime(event.starts_at, event.timezone)}</Typography>
    <Typography>Окончание: {formatEventTime(event.ends_at, event.timezone)}</Typography>
    <Typography>Часовой пояс: {event.timezone}</Typography>
    <Typography>Количество мест: {event.capacity}</Typography>
    {event.status === 'PUBLISHED' && <Button component={RouterLink} to={`/organizer/events/${event.id}/check-in`}>Check-in</Button>}
    {event.status !== 'DRAFT' && <EventStats ownerId={ownerId} eventId={event.id} />}
    {event.status === 'PUBLISHED' && <EventScheduleForm key={`schedule-${event.id}`} event={event} />}
    {event.status === 'PUBLISHED' && <EventCapacityForm key={event.id} event={event} />}
    <Typography sx={{ overflowWrap: 'anywhere' }}>Ссылка события: {event.slug}</Typography>
  </Stack></Paper>;
}
