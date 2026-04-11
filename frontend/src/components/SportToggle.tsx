export type SportCategory = 'racket' | 'golf';

interface SportToggleProps {
  value: SportCategory;
  onChange: (category: SportCategory) => void;
}

export default function SportToggle({ value, onChange }: SportToggleProps) {
  return (
    <div className="flex items-center gap-1 bg-gray-100 dark:bg-gray-800 rounded-lg p-1">
      <button
        onClick={() => onChange('racket')}
        className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
          value === 'racket'
            ? 'bg-white dark:bg-gray-700 text-emerald-600 dark:text-emerald-400 shadow-sm'
            : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
        }`}
      >
        Tennis & Padel
      </button>
      <button
        onClick={() => onChange('golf')}
        className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
          value === 'golf'
            ? 'bg-white dark:bg-gray-700 text-green-600 dark:text-green-400 shadow-sm'
            : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
        }`}
      >
        Golf
      </button>
    </div>
  );
}
