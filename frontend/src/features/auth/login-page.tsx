import { Alert, Button, Container, Link, Paper, Stack, TextField, Typography } from '@mui/material';
import { useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { Link as RouterLink, useNavigate } from 'react-router';
import { ApiError, apiRequest } from '../../api/client';
import type { components } from '../../api/schema';
import { sessionKey, type CurrentUser } from './session';

export function LoginPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string>();
  const [fields, setFields] = useState<Record<string, string>>({});
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    setPending(true);
    setError(undefined);
    setFields({});
    try {
      const body: components['schemas']['LoginRequest'] = { email, password };
      const user = await apiRequest<CurrentUser>('/api/auth/login', { method: 'POST', body: JSON.stringify(body) });
      setPassword('');
      queryClient.setQueryData(sessionKey, user);
      navigate('/');
    } catch (cause) {
      if (cause instanceof ApiError) {
        if (cause.code === 'AUTH_INVALID_CREDENTIALS') setError('Неверный email или пароль');
        else if (cause.code === 'AUTH_RATE_LIMITED') setError('Слишком много попыток. Попробуйте позже');
        else if (cause.code === 'CSRF_INVALID') setError('Защита запроса обновлена. Повторите попытку');
        else if (cause.code === 'VALIDATION_ERROR') {
          const errors: Record<string, string> = {};
          const details = cause.details.fields;
          if (Array.isArray(details)) for (const field of details) {
            if (field && typeof field === 'object' && 'field' in field && 'code' in field && typeof field.field === 'string') {
              errors[field.field] = field.code === 'INVALID_EMAIL' ? 'Укажите корректный email' : 'Пароль должен содержать от 12 до 128 символов';
            }
          }
          setFields(errors);
          setError('Проверьте данные формы');
        } else setError('Не удалось войти. Повторите попытку');
      } else setError('Не удалось отправить запрос. Повторите попытку');
    } finally { setPending(false); }
  }
  return (
    <Container maxWidth="sm" sx={{ py: 8 }}>
      <Paper variant="outlined" sx={{ p: 4 }}>
        <Stack component="form" noValidate onSubmit={submit} spacing={3}>
          <Typography component="h1" variant="h4">Войти</Typography>
          <Typography color="text.secondary">Войдите в аккаунт по email и паролю.</Typography>
          {error && <Alert severity="error">{error}</Alert>}
          <TextField label="Email" name="email" type="email" autoComplete="email" required value={email} onChange={event => setEmail(event.target.value)} error={!!fields.email} helperText={fields.email} disabled={pending} />
          <TextField label="Пароль" name="password" type="password" autoComplete="current-password" required value={password} onChange={event => setPassword(event.target.value)} error={!!fields.password} helperText={fields.password} disabled={pending} />
          <Button type="submit" variant="contained" disabled={pending}>{pending ? 'Входим…' : 'Войти'}</Button>
          <Link component={RouterLink} to="/register">Нет аккаунта? Зарегистрироваться</Link>
        </Stack>
      </Paper>
    </Container>
  );
}
