import { useState, useEffect } from 'react';
import { getAvailability } from '../api';
import type { AvailabilityResponse, AvailabilitySlot } from '../types';

interface GolfCalendarProps {
  userId: string;
}

interface TeeTime {
  date: string;
  hour: number;
  minute: number;
  timeSlot: string;
  courtName: string;
  spots: number;
}

function parseSpots(courtName: string): number {
  const match = courtName.match(/(\d+)\s*spot/i);
  return match ? parseInt(match[1], 10) : 4;
}

function slotToTeeTime(slot: AvailabilitySlot, date: string): TeeTime {
  const [h, m] = slot.timeSlot.split(':').map(Number);
  return {
    date,
    hour: h,
    minute: m,
    timeSlot: slot.timeSlot,
    courtName: slot.courtName,
    spots: parseSpots(slot.courtName),
  };
}

const HOURS = Array.from({ length: 12 }, (_, i) => i + 6); // 06-17

export default function GolfCalendar({ userId }: GolfCalendarProps) {
  const [data, setData] = useState<AvailabilityResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getAvailability(userId, 'golf')
      .then((res) => { if (!cancelled) setData(res); })
      .catch(() => { if (!cancelled) setError('Failed to load golf availability.'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [userId]);

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <svg className="animate-spin h-8 w-8 text-green-600 dark:text-green-400" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
      </div>
    );
  }

  if (error) {
    return <p className="text-center text-red-500 py-8">{error}</p>;
  }

  if (!data || data.days.length === 0) {
    return (
      <div className="text-center py-12 text-gray-400 dark:text-gray-500">
        <p>No golf tee times available yet.</p>
        <p className="text-sm mt-1">Check back after the scraper runs.</p>
      </div>
    );
  }

  // Group tee times by date and hour
  const teeTimes: TeeTime[] = data.days.flatMap((day) =>
    day.slots
      .filter((s) => s.sport === 'golf')
      .map((s) => slotToTeeTime(s, day.date))
  );

  const dates = data.days.map((d) => d.date);

  const getTeeTimes = (date: string, hour: number) =>
    teeTimes.filter((t) => t.date === date && t.hour === hour);

  const formatDate = (dateStr: string) => {
    const d = new Date(dateStr);
    const weekday = d.toLocaleDateString('en', { weekday: 'short' });
    const day = d.getDate();
    const month = d.toLocaleDateString('en', { month: 'short' });
    return { weekday, label: `${day} ${month}` };
  };

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-700">
        <h3 className="font-semibold text-gray-900 dark:text-gray-100">Tee Time Availability</h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 dark:border-gray-700">
              <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 w-16">Time</th>
              {dates.map((date) => {
                const { weekday, label } = formatDate(date);
                return (
                  <th key={date} className="px-2 py-2 text-center text-xs font-medium text-gray-500 dark:text-gray-400 min-w-[80px]">
                    <div>{weekday}</div>
                    <div className="text-[10px] text-gray-400 dark:text-gray-500">{label}</div>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {HOURS.map((hour) => (
              <tr key={hour} className="border-b border-gray-100 dark:border-gray-700/50">
                <td className="px-3 py-1.5 text-xs text-gray-500 dark:text-gray-400 font-mono">
                  {String(hour).padStart(2, '0')}:00
                </td>
                {dates.map((date) => {
                  const times = getTeeTimes(date, hour);
                  return (
                    <td key={date} className="px-1 py-1 align-top">
                      <div className="flex flex-wrap gap-0.5">
                        {times.map((t, i) => (
                          <a
                            key={i}
                            href={`https://www.golfbox.no/portal/public/booking.asp`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-medium cursor-pointer transition-opacity hover:opacity-80 ${
                              t.spots >= 3
                                ? 'bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300'
                                : 'bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300'
                            }`}
                            title={`${t.courtName} - ${t.spots} spot${t.spots !== 1 ? 's' : ''}`}
                          >
                            {t.timeSlot.slice(0, 5)}
                          </a>
                        ))}
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {/* Legend */}
      <div className="px-4 py-2 border-t border-gray-200 dark:border-gray-700 flex items-center gap-4 text-xs text-gray-500 dark:text-gray-400">
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-3 rounded bg-green-100 dark:bg-green-900/40 border border-green-200 dark:border-green-800" />
          3-4 spots
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-3 rounded bg-amber-100 dark:bg-amber-900/40 border border-amber-200 dark:border-amber-800" />
          1-2 spots
        </span>
        <span className="ml-auto">Click a time to open GolfBox</span>
      </div>
    </div>
  );
}
