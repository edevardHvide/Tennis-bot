import confetti from 'canvas-confetti';

interface EasterEggProps {
  visible: boolean;
  onClose: () => void;
}

export default function EasterEgg({ visible, onClose }: EasterEggProps) {
  if (!visible) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ backgroundColor: 'rgba(0,0,0,0.75)' }}
      onClick={onClose}
    >
      <div
        className="bg-white dark:bg-gray-800 rounded-2xl shadow-2xl max-w-md w-full p-8 text-center relative"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          className="absolute top-3 right-3 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors"
        >
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>

        <div className="text-6xl mb-4">🏆</div>

        <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-2">
          YOU FOUND IT!
        </h2>

        <div className="inline-block bg-gradient-to-r from-yellow-400 to-amber-500 text-white text-xs font-bold uppercase tracking-wider px-3 py-1 rounded-full mb-4">
          Easter Egg Discovered
        </div>

        <p className="text-gray-600 dark:text-gray-300 mb-4 leading-relaxed">
          You caught the Easter Bunny! Sharp eyes and great timing.
        </p>

        <div className="bg-green-50 dark:bg-green-900/30 border border-green-200 dark:border-green-700 rounded-xl p-4 mb-4">
          <p className="text-green-800 dark:text-green-300 text-sm font-medium">
            🐰 <strong>Claim your prize:</strong> Screenshot this and reply to the Easter Egg Hunt email.
            The first person to do so wins <strong>Premium First Serve</strong> — your alerts arrive
            2 minutes before everyone else!
          </p>
        </div>

        <p className="text-xs text-gray-400 dark:text-gray-500 italic">
          "In tennis, the smallest margins win the biggest points."
        </p>
      </div>
    </div>
  );
}

export function fireConfetti() {
  const fire = (opts: confetti.Options) =>
    confetti({ ...opts, particleCount: 80, spread: 70, origin: { y: 0.6 } });
  fire({ angle: 60, origin: { x: 0.1 } });
  setTimeout(() => fire({ angle: 90, origin: { x: 0.5 } }), 150);
  setTimeout(() => fire({ angle: 120, origin: { x: 0.9 } }), 300);
}
