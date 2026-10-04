import { Container, CssBaseline, Paper, Stack, Typography } from '@mui/material';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Route, Routes } from 'react-router';

const queryClient = new QueryClient();
function FoundationPage() {
  return (
    <Container maxWidth="sm" sx={{ py: 8 }}>
      <Paper variant="outlined" sx={{ p: 4 }}>
        <Stack spacing={2}>
          <Typography component="h1" variant="h4">Event Registration</Typography>
          <Typography>Foundation is running.</Typography>
          <Typography color="text.secondary">Auth is not implemented yet.</Typography>
        </Stack>
      </Paper>
    </Container>
  );
}
export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <CssBaseline />
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<FoundationPage />} />
          <Route path="/login" element={<FoundationPage />} />
          <Route path="/register" element={<FoundationPage />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
