import { Alert, Button, Container, Link, Paper, Stack, TextField, Typography } from '@mui/material';
import { useState, type FormEvent } from 'react';
import { Link as RouterLink, useNavigate } from 'react-router';
import { ApiError, apiRequest } from '../../api/client';
import type { components } from '../../api/schema';

const fieldMessages: Record<string, string> = {
  INVALID_EMAIL: 'Укажите корректный email',
  PASSWORD_LENGTH: 'Пароль должен содержать от 12 до 128 символов',
};
export function RegisterPage() {
  const navigate = useNavigate();
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
      const body: components['schemas']['RegisterRequest'] = { email, password };
      await apiRequest<components['schemas']['UserResponse']>('/api/auth/register', { method: 'POST', body: JSON.stringify(body) });
      setPassword('');
      navigate('/login');
    } catch (cause) {
      if (cause instanceof ApiError) {
        if (cause.code === 'EMAIL_ALREADY_REGISTERED') setError('Этот email уже зарегистрирован');
        else if (cause.code === 'CSRF_INVALID') setError('Защита запроса обновлена. Повторите попытку');
        else if (cause.code === 'VALIDATION_ERROR') {
          const errors: Record<string, string> = {};
          const details = cause.details.fields;
          if (Array.isArray(details)) for (const field of details) {
            if (field && typeof field === 'object' && 'field' in field && 'code' in field && typeof field.field === 'string' && typeof field.code === 'string') {
              errors[field.field] = fieldMessages[field.code] ?? 'Проверьте значение';
            }
          }
          setFields(errors);
          setError('Проверьте данные формы');
        } else setError('Не удалось создать аккаунт');
      } else setError('Не удалось отправить запрос. Повторите попытку');
    } finally { setPending(false); }
  }
  return (
    <Container maxWidth="sm" sx={{ py: 8 }}>
      <Paper variant="outlined" sx={{ p: 4 }}>
        <Stack component="form" noValidate onSubmit={submit} spacing={3}>
          <Typography component="h1" variant="h4">Создать аккаунт</Typography>
          <Typography color="text.secondary">После регистрации перейдите к входу.</Typography>
          {error && <Alert severity="error">{error}</Alert>}
          <TextField label="Email" name="email" type="email" autoComplete="email" required value={email} onChange={event => setEmail(event.target.value)} error={!!fields.email} helperText={fields.email} disabled={pending} />
          <TextField label="Пароль" name="password" type="password" autoComplete="new-password" required value={password} onChange={event => setPassword(event.target.value)} error={!!fields.password} helperText={fields.password ?? 'От 12 до 128 символов'} disabled={pending} />
          <Button type="submit" variant="contained" disabled={pending}>{pending ? 'Создаём аккаунт…' : 'Создать аккаунт'}</Button>
          <Link component={RouterLink} to="/login">Уже есть аккаунт? Войти</Link>
        </Stack>
      </Paper>
    </Container>
  );
}
