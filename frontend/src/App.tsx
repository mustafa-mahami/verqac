import { AppShell, Button, Center, Group, Loader, Text, useDirection } from '@mantine/core';
import { useTranslation } from 'react-i18next';
import { Navigate, Route, Routes } from 'react-router-dom';
import { useAuth } from './auth';
import { applyLanguage, pick } from './i18n';
import Login from './pages/Login';
import Projects from './pages/Projects';
import Register from './pages/Register';

export function LanguageButton() {
  const { t, i18n } = useTranslation();
  const { setDirection } = useDirection();
  const toggle = () => {
    const next = i18n.language === 'ar' ? 'en' : 'ar';
    applyLanguage(next);
    setDirection(next === 'ar' ? 'rtl' : 'ltr');
  };
  return (
    <Button variant="subtle" size="compact-sm" onClick={toggle}>
      {t('lang.switch')}
    </Button>
  );
}

function Shell() {
  const { t } = useTranslation();
  const { me, signOut } = useAuth();
  return (
    <AppShell header={{ height: 56 }} padding="md">
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Text fw={700} size="lg" c="verqac.7">
            {t('app.name')}
          </Text>
          <Group gap="xs">
            {me && <Text size="sm" c="dimmed">{pick(me.user, 'full_name')}</Text>}
            <LanguageButton />
            <Button variant="light" size="compact-sm" onClick={signOut}>
              {t('auth.logout')}
            </Button>
          </Group>
        </Group>
      </AppShell.Header>
      <AppShell.Main>
        <Routes>
          <Route path="/projects" element={<Projects />} />
          <Route path="*" element={<Navigate to="/projects" replace />} />
        </Routes>
      </AppShell.Main>
    </AppShell>
  );
}

export default function App() {
  const { me, loading } = useAuth();
  if (loading)
    return (
      <Center h="100vh">
        <Loader />
      </Center>
    );
  if (!me)
    return (
      <Routes>
        <Route path="/register" element={<Register />} />
        <Route path="*" element={<Login />} />
      </Routes>
    );
  return <Shell />;
}
