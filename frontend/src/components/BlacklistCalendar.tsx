import { useState } from 'react';

interface BlacklistCalendarProps {
  blacklistedDates: string[];
  onToggle: (dates: string[]) => void;
  saving: boolean;
}

function getDayLabel(dateStr: string): { short: string; num: string } {
  const d = new Date(dateStr + 'T12:00:00');
  return {
    short: d.toLocaleDateString('en-US', { weekday: 'short' }),
    num: d.toLocaleDateString('en-US', { day: 'numeric', month: 'short' }),
  };
}

function getNext14Days(): string[] {
  const dates: string[] = [];
  const today = new Date();
  for (let i = 0; i < 14; i++) {
    const d = new Date(today);
    d.setDate(today.getDate() + i);
    dates.push(d.toISOString().slice(0, 10));
  }
  return dates;
}

export default function BlacklistCalendar({ blacklistedDates, onToggle, saving }: BlacklistCalendarProps) {
  const [open, setOpen] = useState(false);
  const days = getNext14Days();
  const blacklistSet = new Set(blacklistedDates);

  const handleToggle = (dateStr: string) => {
    const next = new Set(blacklistSet);
    if (next.has(dateStr)) {
      next.delete(dateStr);
    } else {
      next.add(dateStr);
    }
    onToggle(Array.from(next).sort());
  };

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-5 py-4 text-left hover:bg-gray-50 dark:hover:bg-gray-750 transition-colors"
      >
        <div className="flex items-center gap-2">
          {saving ? (
            <svg className="animate-spin h-4 w-4 text-green-600 dark:text-green-400" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          ) : (
            <svg className="w-4 h-4 text-gray-500 dark:text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 9v6m4-6v6m7-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          )}
          <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Pause Alerts</span>
          {blacklistedDates.length > 0 && (
            <span className="text-xs bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300 px-2 py-0.5 rounded-full border border-amber-200 dark:border-amber-700">
              {blacklistedDates.length} paused
            </span>
          )}
        </div>
        <svg
          className={`w-4 h-4 text-gray-400 transition-transform ${open ? 'rotate-180' : ''}`}
          fill="none" stroke="currentColor" viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {open && (
        <div className="px-5 pb-5 border-t border-gray-100 dark:border-gray-700">
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-3 mb-3">
            Tap a date to skip notifications for that day.
          </p>
          <div className="grid grid-cols-7 gap-1.5">
            {days.map((dateStr) => {
              const { short, num } = getDayLabel(dateStr);
              const paused = blacklistSet.has(dateStr);
              return (
                <button
                  key={dateStr}
                  onClick={() => handleToggle(dateStr)}
                  disabled={saving}
                  title={dateStr}
                  className={`flex flex-col items-center py-2 px-1 rounded-lg text-xs font-medium transition-colors disabled:opacity-50 ${
                    paused
                      ? 'bg-amber-100 dark:bg-amber-900/40 text-amber-800 dark:text-amber-300 ring-1 ring-amber-400 dark:ring-amber-600'
                      : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                  }`}
                >
                  <span className="font-semibold">{short}</span>
                  <span className="mt-0.5 opacity-80">{num}</span>
                </button>
              );
            })}
          </div>
          {blacklistedDates.length > 0 && (
            <p className="mt-3 text-xs text-amber-600 dark:text-amber-400">
              {blacklistedDates.length} day{blacklistedDates.length > 1 ? 's' : ''} paused
            </p>
          )}
        </div>
      )}
    </div>
  );
}
