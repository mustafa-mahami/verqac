import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import ar from './locales/ar.json';
import en from './locales/en.json';

const saved = (() => {
  try {
    return localStorage.getItem('verqac.lang');
  } catch {
    return null;
  }
})();

i18n.use(initReactI18next).init({
  resources: { ar: { translation: ar }, en: { translation: en } },
  lng: saved === 'en' ? 'en' : 'ar',
  fallbackLng: 'ar',
  interpolation: { escapeValue: false },
});

export function applyLanguage(lng: 'ar' | 'en') {
  i18n.changeLanguage(lng);
  document.documentElement.lang = lng;
  document.documentElement.dir = lng === 'ar' ? 'rtl' : 'ltr';
  try {
    localStorage.setItem('verqac.lang', lng);
  } catch {
    /* storage unavailable: language just won't persist */
  }
}

/** Pick the Arabic or English field of a bilingual record. */
export function pick<T extends object>(obj: T, base: string): string {
  const lng = i18n.language === 'en' ? 'en' : 'ar';
  const o = obj as Record<string, unknown>;
  return String(o[`${base}_${lng}`] ?? o[`${base}_ar`] ?? '');
}

export default i18n;
