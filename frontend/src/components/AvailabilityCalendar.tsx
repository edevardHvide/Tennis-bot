import { useState, useEffect, useCallback } from 'react';
import type { AvailabilityResponse, AvailabilitySlot } from '../types';
import { DAY_SHORT_LABELS, type DayOfWeek } from '../types';
import { getAvailability } from '../api';

interface Props {
  userId: string;
}

const FACILITY_COLORS: Record<string, string> = {
  ota: '#34d399',
  bergentennisarena: '#60a5fa',
  furuset: '#fb923c',
  interpadel: '#a78bfa',
  nordicpadel: '#f472b6',
  nordstrand: '#fbbf24',
  voldslokka: '#2dd4bf',
  bergenpadelklubb: '#c084fc',
  interpadelbergen: '#f87171',
  frogner: '#4ade80',
  ullern: '#38bdf8',
  heming: '#e879f9',
  holmenkollen: '#fb7185',
};

function timeToMinutes(t: string): number {
  const [h, m] = t.split(':').map(Number);
  return h * 60 + m;
}

function formatTimeAgo(isoString: string): string {
  const then = new Date(isoString).getTime();
  const now = Date.now();
  const mins = Math.round((now - then) / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ${mins % 60}m ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function formatTime(isoString: string): string {
  return new Date(isoString).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function getTimeSlots(slots: AvailabilitySlot[]): string[] {
  const set = new Set<string>();
  for (const s of slots) {
    set.add(s.timeSlot);
  }
  return Array.from(set).sort((a, b) => timeToMinutes(a.split('-')[0]) - timeToMinutes(b.split('-')[0]));
}

export default function AvailabilityCalendar({ userId }: Props) {
  const [data, setData] = useState<AvailabilityResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [expanded, setExpanded] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      const result = await getAvailability(userId);
      setData(result);
      setError('');
    } catch {
      setError('Failed to load availability.');
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  if (loading) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm p-6">
        <div className="flex justify-center py-8">
          <svg className="animate-spin h-6 w-6 text-green-600 dark:text-green-400" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm p-6">
        <p className="text-red-500 dark:text-red-400 text-sm text-center">{error}</p>
      </div>
    );
  }

  if (!data || data.days.length === 0 || data.facilities.length === 0) {
    return null;
  }

  // Collect all unique time slots across all days
  const allSlots = data.days.flatMap((d) => d.slots);
  const allTimeSlots = getTimeSlots(allSlots);

  // Compute freshness info
  const freshnessEntries = Object.entries(data.freshness);
  const oldestUpdate = freshnessEntries.length > 0
    ? freshnessEntries.reduce((oldest, [, v]) => v.updatedAt < oldest ? v.updatedAt : oldest, freshnessEntries[0][1].updatedAt)
    : null;

  const totalSlots = allSlots.length;

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden">
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full px-6 py-4 flex items-center justify-between hover:bg-gray-50 dark:hover:bg-gray-750 transition-colors"
      >
        <div className="flex items-center gap-3">
          <svg className="w-5 h-5 text-green-600 dark:text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
          <span className="font-semibold text-gray-900 dark:text-gray-100">Court Availability</span>
          <span className="text-xs bg-green-100 dark:bg-green-900/50 text-green-700 dark:text-green-400 px-2 py-0.5 rounded-full font-medium">
            {totalSlots} slot{totalSlots !== 1 ? 's' : ''}
          </span>
        </div>
        <div className="flex items-center gap-3">
          {/* Freshness indicator */}
          {oldestUpdate && (
            <span className="text-xs text-gray-400 dark:text-gray-500 hidden sm:inline">
              Updated {formatTimeAgo(oldestUpdate)}
            </span>
          )}
          {data.nextUpdateAt && (
            <span className="text-xs text-gray-400 dark:text-gray-500 hidden sm:inline">
              · Next: {formatTime(data.nextUpdateAt)}
            </span>
          )}
          <svg
            className={`w-5 h-5 text-gray-400 transition-transform ${expanded ? 'rotate-180' : ''}`}
            fill="none" stroke="currentColor" viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </button>

      {expanded && (
        <div className="px-6 pb-6">
          {/* Freshness bar (mobile) */}
          <div className="sm:hidden mb-3 flex items-center gap-2 text-xs text-gray-400 dark:text-gray-500">
            <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
            {oldestUpdate && <span>Updated {formatTimeAgo(oldestUpdate)}</span>}
            {data.nextUpdateAt && <span>· Next: {formatTime(data.nextUpdateAt)}</span>}
          </div>

          {totalSlots === 0 ? (
            <div className="text-center py-8 text-gray-400 dark:text-gray-500 text-sm">
              No available courts matching your preferences in the next 7 days.
            </div>
          ) : (
            <>
              {/* Week grid */}
              <div className="overflow-x-auto -mx-2">
                <div className="inline-grid min-w-full" style={{ gridTemplateColumns: `80px repeat(${data.days.length}, minmax(100px, 1fr))` }}>
                  {/* Header row */}
                  <div className="sticky left-0 bg-white dark:bg-gray-800 z-10" />
                  {data.days.map((day) => {
                    const dateObj = new Date(day.date + 'T00:00:00');
                    const isToday = day.date === new Date().toISOString().split('T')[0];
                    return (
                      <div
                        key={day.date}
                        className={`text-center py-2 text-xs font-medium border-b border-gray-100 dark:border-gray-700 ${
                          isToday ? 'text-green-600 dark:text-green-400' : 'text-gray-500 dark:text-gray-400'
                        }`}
                      >
                        <div className="font-semibold">{DAY_SHORT_LABELS[day.weekday as DayOfWeek] ?? day.weekday}</div>
                        <div className="text-[10px] text-gray-400 dark:text-gray-500">
                          {dateObj.getDate()}/{dateObj.getMonth() + 1}
                        </div>
                        {isToday && <div className="w-1.5 h-1.5 rounded-full bg-green-500 mx-auto mt-1" />}
                      </div>
                    );
                  })}

                  {/* Time slot rows */}
                  {allTimeSlots.map((timeSlot) => (
                    <>
                      <div
                        key={`label-${timeSlot}`}
                        className="sticky left-0 bg-white dark:bg-gray-800 z-10 pr-2 py-1.5 text-[11px] text-gray-400 dark:text-gray-500 font-mono text-right border-b border-gray-50 dark:border-gray-700/50 flex items-center justify-end"
                      >
                        {timeSlot.split('-')[0]}
                      </div>
                      {data.days.map((day) => {
                        const cellSlots = day.slots.filter((s) => s.timeSlot === timeSlot);
                        return (
                          <div
                            key={`${day.date}-${timeSlot}`}
                            className="py-1.5 px-1 border-b border-gray-50 dark:border-gray-700/50 flex flex-wrap gap-0.5"
                          >
                            {cellSlots.map((slot, i) => (
                              <div
                                key={i}
                                className="text-[10px] leading-tight px-1.5 py-0.5 rounded-md truncate max-w-full"
                                style={{
                                  backgroundColor: `${FACILITY_COLORS[slot.facilityId] ?? '#6b7280'}20`,
                                  color: FACILITY_COLORS[slot.facilityId] ?? '#6b7280',
                                  border: `1px solid ${FACILITY_COLORS[slot.facilityId] ?? '#6b7280'}40`,
                                }}
                                title={`${slot.courtName} at ${slot.facilityId} (${slot.sport})`}
                              >
                                {slot.courtName}
                              </div>
                            ))}
                          </div>
                        );
                      })}
                    </>
                  ))}
                </div>
              </div>

              {/* Legend */}
              <div className="mt-4 flex flex-wrap gap-3">
                {data.facilities.map((f) => (
                  <div key={f.facilityId} className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400">
                    <div
                      className="w-2.5 h-2.5 rounded-full"
                      style={{ backgroundColor: FACILITY_COLORS[f.facilityId] ?? '#6b7280' }}
                    />
                    {f.displayName}
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
