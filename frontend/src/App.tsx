import { AppShell, Button, Center, Group, Loader, Text, useDirection } from '@mantine/core';
import { useTranslation } from 'react-i18next';
import { Link, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { useAuth } from './auth';
import { applyLanguage, pick } from './i18n';
import Bell from './pages/Bell';
import Inbox from './pages/Inbox';
import Invite from './pages/Invite';
import Verify from './pages/Verify';
import Login from './pages/Login';
import OrgPage from './pages/OrgPage';
import ProjectPage from './pages/ProjectPage';
import RecordPage from './pages/RecordPage';
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

function NavLink({ to, label }: { to: string; label: string }) {
  const { pathname } = useLocation();
  const active = pathname === to || pathname.startsWith(`${to}/`);
  return (
    <Text component={Link} to={to} size="sm" fw={active ? 600 : 400} c={active ? 'verqac.7' : 'dimmed'}>
      {label}
    </Text>
  );
}

function Shell() {
  const { t } = useTranslation();
  const { me, signOut } = useAuth();
  const isAdmin = (me?.orgs ?? []).some((m) => m.org_role === 'admin');
  return (
    <AppShell header={{ height: 56 }} padding="md">
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Group gap="lg">
            <Text fw={700} size="lg" c="verqac.7" component={Link} to="/projects">
              {t('app.name')}
            </Text>
            <NavLink to="/inbox" label={t('nav.inbox')} />
            <NavLink to="/projects" label={t('nav.projects')} />
            {isAdmin && <NavLink to="/org" label={t('nav.orgUsers')} />}
          </Group>
          <Group gap="xs">
            <Bell />
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
          <Route path="/inbox" element={<Inbox />} />
          <Route path="/projects" element={<Projects />} />
          <Route path="/projects/:id" element={<ProjectPage />} />
          <Route path="/records/:id" element={<RecordPage />} />
          <Route path="/org" element={<OrgPage />} />
          <Route path="*" element={<Navigate to="/inbox" replace />} />
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
  return (
    <Routes>
      {/* an invitation link works signed in or not */}
      <Route path="/invite/:token" element={<Invite />} />
      {/* the QR on a printed reply opens this, for anyone */}
      <Route path="/v/:stamp" element={<Verify />} />
      {!me && <Route path="/register" element={<Register />} />}
      <Route path="*" element={me ? <Shell /> : <Login />} />
    </Routes>
  );
}
