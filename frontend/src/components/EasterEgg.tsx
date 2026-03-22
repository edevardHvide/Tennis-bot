import { useState, useEffect } from 'react';
import confetti from 'canvas-confetti';

export default function EasterEgg() {
  const [found, setFound] = useState(false);
  const [wobble, setWobble] = useState(false);

  // Subtle wobble every 8 seconds to give a tiny hint
  useEffect(() => {
    const interval = setInterval(() => {
      setWobble(true);
      setTimeout(() => setWobble(false), 600);
    }, 8000);
    return () => clearInterval(interval);
  }, []);

  const handleClick = () => {
    setFound(true);
    // Triple confetti burst
    const fire = (opts: confetti.Options) =>
      confetti({ ...opts, particleCount: 80, spread: 70, origin: { y: 0.6 } });
    fire({ angle: 60, origin: { x: 0.1 } });
    setTimeout(() => fire({ angle: 90, origin: { x: 0.5 } }), 150);
    setTimeout(() => fire({ angle: 120, origin: { x: 0.9 } }), 300);
  };

  return (
    <>
      {/* The hidden tennis ball — tiny, nearly invisible, bottom-right of content area */}
      <div
        onClick={handleClick}
        title=""
        style={{
          position: 'fixed',
          bottom: 18,
          right: 22,
          width: 9,
          height: 9,
          borderRadius: '50%',
          background: 'radial-gradient(circle at 35% 35%, #d4e157, #9e9d24)',
          opacity: wobble ? 0.35 : 0.12,
          cursor: 'default',
          transition: 'opacity 0.3s ease, transform 0.3s ease',
          transform: wobble ? 'scale(1.3)' : 'scale(1)',
          zIndex: 10,
        }}
        onMouseEnter={(e) => {
          (e.target as HTMLElement).style.opacity = '0.4';
          (e.target as HTMLElement).style.cursor = 'pointer';
        }}
        onMouseLeave={(e) => {
          (e.target as HTMLElement).style.opacity = '0.12';
          (e.target as HTMLElement).style.cursor = 'default';
        }}
      />

      {/* Celebration modal */}
      {found && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ backgroundColor: 'rgba(0,0,0,0.75)' }}
          onClick={() => setFound(false)}
        >
          <div
            className="bg-white dark:bg-gray-800 rounded-2xl shadow-2xl max-w-md w-full p-8 text-center relative"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Close button */}
            <button
              onClick={() => setFound(false)}
              className="absolute top-3 right-3 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>

            {/* Trophy */}
            <div className="text-6xl mb-4">🏆</div>

            <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-2">
              YOU FOUND IT!
            </h2>

            <div className="inline-block bg-gradient-to-r from-yellow-400 to-amber-500 text-white text-xs font-bold uppercase tracking-wider px-3 py-1 rounded-full mb-4">
              Easter Egg Discovered
            </div>

            <p className="text-gray-600 dark:text-gray-300 mb-4 leading-relaxed">
              You spotted the hidden tennis ball! You've got the sharpest eyes on the court.
            </p>

            <div className="bg-green-50 dark:bg-green-900/30 border border-green-200 dark:border-green-700 rounded-xl p-4 mb-4">
              <p className="text-green-800 dark:text-green-300 text-sm font-medium">
                🎾 <strong>Claim your prize:</strong> Screenshot this and reply to the Easter Egg Hunt email.
                The first person to do so wins <strong>Premium First Serve</strong> — your alerts arrive
                2 minutes before everyone else!
              </p>
            </div>

            <p className="text-xs text-gray-400 dark:text-gray-500 italic">
              "In tennis, the smallest margins win the biggest points."
            </p>
          </div>
        </div>
      )}
    </>
  );
}
