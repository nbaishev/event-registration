import { MyRegistrationsPage } from './features/registrations/my-registrations-page';
import { CssBaseline } from '@mui/material';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState } from 'react';
import { BrowserRouter, Route, Routes } from 'react-router';
import { AccountPage } from './features/auth/account-page';
import { LoginPage } from './features/auth/login-page';
import { SessionBoundary } from './features/auth/session';
import { RegisterPage } from './features/auth/register-page';
import { OrganizerLayout } from './features/events/organizer-layout';
import { EventCreatePage } from './features/events/event-create-page';
import { EventListPage } from './features/events/event-list-page';
import { EventDetailPage } from './features/events/event-detail-page';
import { PublicEventPage } from './features/events/public-event-page';
import { EventEditPage } from './features/events/event-edit-page';

export function App({ client }: { client?: QueryClient } = {}) {
  const [queryClient] = useState(() => client ?? new QueryClient());
  return (
    <QueryClientProvider client={queryClient}>
      <CssBaseline />
      <BrowserRouter>
        <SessionBoundary />
        <Routes>
          <Route path="/events/:slug" element={<PublicEventPage />} />
          <Route path="/me/registrations" element={<MyRegistrationsPage />} />
          <Route path="/" element={<AccountPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/organizer/events" element={<OrganizerLayout />}>
            <Route index element={<EventListPage />} />
            <Route path="new" element={<EventCreatePage />} />
            <Route path=":eventId/edit" element={<EventEditPage />} />
            <Route path=":eventId" element={<EventDetailPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
