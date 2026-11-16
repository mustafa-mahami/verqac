import { Button } from '@mantine/core';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

/** One back button for every inner screen; the arrow follows the reading direction. */
export default function BackButton({ to, label }: { to: string; label: string }) {
  const { i18n } = useTranslation();
  return (
    <Button component={Link} to={to} variant="subtle" size="compact-md" px={4} style={{ alignSelf: 'flex-start' }}
      leftSection={<span aria-hidden style={{ fontSize: 18 }}>{i18n.language === 'en' ? '←' : '→'}</span>}>
      {label}
    </Button>
  );
}
