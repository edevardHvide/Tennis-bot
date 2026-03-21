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
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm p-5">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100">Pause Alerts</h3>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
            Tap a date to skip notifications for that day.
          </p>
        </div>
        {saving && (
          <svg className="animate-spin h-4 w-4 text-green-600 dark:text-green-400" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
        )}
      </div>
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
  );
}
