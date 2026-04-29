import { useEffect, useState, useCallback, useRef } from 'react';
import { driver, DriveStep } from 'driver.js';
import { useTranslation } from 'react-i18next';
import 'driver.js/dist/driver.css';

const ONBOARDING_VERSION = 2;
const ONBOARDING_KEY = 'useit_onboarding_version';
const ONBOARDING_ENABLED = import.meta.env.VITE_ENABLE_ONBOARDING !== 'false';

export function useOnboarding(isSidebarMode: boolean = false) {
  const { t } = useTranslation();
  const [showWelcome, setShowWelcome] = useState(false);
  const initRef = useRef(false);

  const [hasCompleted, setHasCompleted] = useState(() => {
    if (!ONBOARDING_ENABLED) return true;
    const stored = localStorage.getItem(ONBOARDING_KEY);
    return stored !== null && Number(stored) >= ONBOARDING_VERSION;
  });

  const markCompleted = useCallback(() => {
    localStorage.setItem(ONBOARDING_KEY, String(ONBOARDING_VERSION));
    setHasCompleted(true);
    setShowWelcome(false);
  }, []);

  const startTour = useCallback(() => {
    setShowWelcome(false);

    const workspaceSteps: DriveStep[] = [
      {
        element: '[data-tour="left-panel"]',
        popover: {
          title: t('steps.leftPanel.title'),
          description: t('steps.leftPanel.description'),
          side: 'right',
          align: 'center',
        },
      },
      {
        element: '[data-tour="chat-panel"]',
        popover: {
          title: t('steps.chatPanel.title'),
          description: t('steps.chatPanel.description'),
          side: 'left',
          align: 'start',
        },
      },
      {
        element: '[data-tour="main-viewer"]',
        popover: {
          title: t('steps.mainViewer.title'),
          description: t('steps.mainViewer.description'),
          side: 'left',
          align: 'center',
        },
      },
      {
        element: '[data-tour="control-panel"]',
        popover: {
          title: t('steps.controlPanel.title'),
          description: t('steps.controlPanel.description'),
          side: 'top',
          align: 'center',
        },
      },
      {
        element: '[data-tour="work-tabs"]',
        popover: {
          title: t('steps.workTabs.title'),
          description: t('steps.workTabs.description'),
          side: 'bottom',
          align: 'center',
        },
      },
    ];

    const sidebarSteps: DriveStep[] = [
      {
        element: '[data-tour="chat-panel"]',
        popover: {
          title: t('steps.chatPanel.title'),
          description: t('steps.chatPanel.description'),
          side: 'left',
          align: 'start',
        },
      },
      {
        element: '[data-tour="main-viewer"]',
        popover: {
          title: t('steps.mainViewer.title'),
          description: t('steps.mainViewer.description'),
          side: 'left',
          align: 'center',
        },
      },
    ];

    const steps = isSidebarMode ? sidebarSteps : workspaceSteps;

    const driverObj = driver({
      showProgress: true,
      animate: true,
      allowClose: true,
      overlayColor: 'rgba(0, 0, 0, 0.6)',
      stagePadding: 8,
      stageRadius: 8,
      popoverClass: 'useit-driver-popover',
      progressText: '{{current}} / {{total}}',
      nextBtnText: t('buttons.next'),
      prevBtnText: t('buttons.prev'),
      doneBtnText: t('buttons.done'),
      onDestroyStarted: () => {
        markCompleted();
        driverObj.destroy();
      },
      steps,
    });

    driverObj.drive();
  }, [t, isSidebarMode, markCompleted]);

  const resetTour = useCallback(() => {
    localStorage.removeItem(ONBOARDING_KEY);
    setHasCompleted(false);
  }, []);

  useEffect(() => {
    if (!hasCompleted && !initRef.current) {
      initRef.current = true;
      const timer = setTimeout(() => {
        setShowWelcome(true);
      }, 600);
      return () => clearTimeout(timer);
    }
  }, [hasCompleted]);

  return {
    hasCompleted,
    showWelcome,
    startTour,
    resetTour,
    skipWelcome: markCompleted,
  };
}
