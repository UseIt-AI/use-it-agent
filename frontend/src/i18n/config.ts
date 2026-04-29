import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

// Import English translations
import enSettings from './locales/en/settings.json';
import enWorkspace from './locales/en/workspace.json';
import enOnboarding from './locales/en/onboarding.json';
import enAuth from './locales/en/auth.json';
import enMobile from './locales/en/mobile.json';
import enExplore from './locales/en/explore.json';

// Import Chinese translations
import zhSettings from './locales/zh/settings.json';
import zhWorkspace from './locales/zh/workspace.json';
import zhOnboarding from './locales/zh/onboarding.json';
import zhAuth from './locales/zh/auth.json';
import zhMobile from './locales/zh/mobile.json';
import zhExplore from './locales/zh/explore.json';

// Always default to English (other languages coming soon)
i18n
  .use(initReactI18next)
  .init({
    resources: {
      en: {
        translation: {
          ...enSettings,
          ...enWorkspace,
          ...enOnboarding,
          ...enAuth,
          ...enMobile,
          ...enExplore
        }
      },
      zh: {
        translation: {
          ...zhSettings,
          ...zhWorkspace,
          ...zhOnboarding,
          ...zhAuth,
          ...zhMobile,
          ...zhExplore
        }
      }
    },
    lng: 'en',
    fallbackLng: 'en',
    interpolation: {
      escapeValue: false // React 已经处理了 XSS
    }
  });

export default i18n;

