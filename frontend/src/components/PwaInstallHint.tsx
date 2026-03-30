import { useState, useEffect } from 'react';

interface BeforeInstallPromptEvent extends Event {
  prompt(): Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

export default function PwaInstallHint() {
  const [show, setShow] = useState(false);
  const [deferredPrompt, setDeferredPrompt] = useState<BeforeInstallPromptEvent | null>(null);
  const [isIos, setIsIos] = useState(false);

  useEffect(() => {
    // Don't show if already in standalone mode (PWA installed)
    if (window.matchMedia('(display-mode: standalone)').matches) return;
    if ((navigator as any).standalone) return; // iOS standalone

    // Don't show if dismissed recently (7 days)
    const dismissed = localStorage.getItem('pwa-hint-dismissed');
    if (dismissed && Date.now() - Number(dismissed) < 7 * 24 * 60 * 60 * 1000) return;

    // Only show on mobile
    const isMobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent);
    if (!isMobile) return;

    const isIosDevice = /iPhone|iPad|iPod/i.test(navigator.userAgent);
    setIsIos(isIosDevice);

    // On Android/Chrome, capture the install prompt
    const handler = (e: Event) => {
      e.preventDefault();
      setDeferredPrompt(e as BeforeInstallPromptEvent);
      setShow(true);
    };
    window.addEventListener('beforeinstallprompt', handler);

    // On iOS, show hint after a short delay (no native prompt)
    if (isIosDevice) {
      const timer = setTimeout(() => setShow(true), 2000);
      return () => {
        clearTimeout(timer);
        window.removeEventListener('beforeinstallprompt', handler);
      };
    }

    return () => window.removeEventListener('beforeinstallprompt', handler);
  }, []);

  const handleInstall = async () => {
    if (deferredPrompt) {
      await deferredPrompt.prompt();
      const { outcome } = await deferredPrompt.userChoice;
      if (outcome === 'accepted') {
        setShow(false);
      }
      setDeferredPrompt(null);
    }
  };

  const handleDismiss = () => {
    setShow(false);
    localStorage.setItem('pwa-hint-dismissed', String(Date.now()));
  };

  if (!show) return null;

  return (
    <div className="fixed bottom-4 left-4 right-4 z-50 animate-slide-up">
      <div className="mx-auto max-w-sm rounded-2xl bg-white/95 dark:bg-slate-800/95 backdrop-blur-lg shadow-lg shadow-black/10 border border-slate-200/60 dark:border-slate-700/60 p-4">
        <div className="flex items-start gap-3">
          <div className="shrink-0 text-2xl mt-0.5">🎾</div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-slate-900 dark:text-white">
              Install Court Alerts
            </p>
            {isIos ? (
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 leading-relaxed">
                Tap{' '}
                <span className="inline-flex items-center align-middle">
                  <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <path d="M12 3v12m0-12l4 4m-4-4L8 7" strokeLinecap="round" strokeLinejoin="round" />
                    <path d="M4 14v5a2 2 0 002 2h12a2 2 0 002-2v-5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </span>
                {' '}then <strong>"Add to Home Screen"</strong>
              </p>
            ) : (
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 leading-relaxed">
                Add to your home screen for quick access
              </p>
            )}
          </div>
          <div className="flex items-center gap-1 shrink-0">
            {!isIos && deferredPrompt && (
              <button
                onClick={handleInstall}
                className="rounded-lg bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-700 transition-colors"
              >
                Install
              </button>
            )}
            <button
              onClick={handleDismiss}
              className="rounded-lg p-1.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
              aria-label="Dismiss"
            >
              <svg className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor">
                <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
