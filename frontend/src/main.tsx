import '@fontsource/ibm-plex-sans-arabic/400.css';
import '@fontsource/ibm-plex-sans-arabic/600.css';
import '@fontsource/ibm-plex-sans-arabic/700.css';
import '@mantine/core/styles.css';
import '@mantine/notifications/styles.css';

import { DirectionProvider, MantineProvider, createTheme } from '@mantine/core';
import { Notifications } from '@mantine/notifications';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import { AuthProvider } from './auth';
import i18n, { applyLanguage } from './i18n';

applyLanguage(i18n.language === 'en' ? 'en' : 'ar');

const theme = createTheme({
  fontFamily: "'IBM Plex Sans Arabic', system-ui, sans-serif",
  headings: { fontFamily: "'IBM Plex Sans Arabic', system-ui, sans-serif", fontWeight: '600' },
  primaryColor: 'verqac',
  colors: {
    verqac: ['#eaf0f7', '#d2deec', '#a5bcd9', '#7499c5', '#4b7ab3', '#2f63a3', '#1f4f8c', '#1f3a5f', '#172d4a', '#0f1f34'],
  },
  primaryShade: 7,
  defaultRadius: 'md',
});

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } } });

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <DirectionProvider initialDirection={document.documentElement.dir === 'ltr' ? 'ltr' : 'rtl'}>
      <MantineProvider theme={theme}>
        <Notifications position="top-center" />
        <QueryClientProvider client={queryClient}>
          <BrowserRouter>
            <AuthProvider>
              <App />
            </AuthProvider>
          </BrowserRouter>
        </QueryClientProvider>
      </MantineProvider>
    </DirectionProvider>
  </StrictMode>,
);
