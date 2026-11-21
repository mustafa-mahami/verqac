import '@fontsource/ibm-plex-sans-arabic/400.css';
import '@fontsource/ibm-plex-sans-arabic/600.css';
import '@fontsource/ibm-plex-sans-arabic/700.css';
import '@mantine/core/styles.css';
import '@mantine/notifications/styles.css';
import './app.css';

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
    // calm status colours: muted tones that sit between the slate greys and the navy (shade 6 is the base)
    blue: ['#f1f3f6', '#dee5ec', '#c0ccda', '#a1b3c7', '#8099b4', '#6381a3', '#4a6d94', '#3f5f83', '#355171', '#2a4360'],
    green: ['#f2f6f4', '#e1eae6', '#c6d6ce', '#aac2b6', '#8cad9c', '#729a86', '#5b8a72', '#4d7767', '#40635c', '#325051'],
    teal: ['#f1f5f5', '#dfe9e9', '#c1d4d4', '#a3c0bf', '#84aaa9', '#689695', '#4f8584', '#437376', '#386067', '#2c4e59'],
    orange: ['#f9f6f1', '#f1eade', '#e3d6c0', '#d6c2a1', '#c8ad80', '#bb9a63', '#b08a4a', '#937746', '#766342', '#59503e'],
    yellow: ['#f9f7f1', '#f1eddf', '#e4dcc1', '#d7caa3', '#cab884', '#bea868', '#b39a4f', '#95844a', '#786e45', '#5a5840'],
    red: ['#f8f2f2', '#efe2e1', '#e0c6c4', '#d1aba8', '#c18e89', '#b2746f', '#a65d57', '#8b5251', '#70474a', '#543c44'],
    gray: ['#f7f8fa', '#eef0f3', '#dfe3e8', '#c9cfd7', '#aab2bd', '#8e97a3', '#7a8594', '#5d6877', '#434d5b', '#2a3340'],
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
