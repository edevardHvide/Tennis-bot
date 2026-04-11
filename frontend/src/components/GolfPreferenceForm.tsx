import { useState } from 'react';
import type { PreferenceFormData, DayOfWeek } from '../types';
import { ALL_DAYS, DAY_SHORT_LABELS, FACILITIES } from '../types';

interface GolfPreferenceFormProps {
  onSubmit: (data: PreferenceFormData) => Promise<void>;
  onCancel: () => void;
}

const GOLF_FACILITIES = FACILITIES.filter((f) => f.sports.includes('golf'));

export default function GolfPreferenceForm({ onSubmit, onCancel }: GolfPreferenceFormProps) {
  const [facilityId, setFacilityId] = useState(GOLF_FACILITIES[0]?.id ?? '');
  const [days, setDays] = useState<DayOfWeek[]>([]);
  const [timeFrom, setTimeFrom] = useState('06:00');
  const [timeTo, setTimeTo] = useState('17:00');
  const [minSpots, setMinSpots] = useState(1);
  const [submitting, setSubmitting] = useState(false);

  const toggleDay = (day: DayOfWeek) => {
    setDays((prev) => (prev.includes(day) ? prev.filter((d) => d !== day) : [...prev, day]));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (days.length === 0) return;
    setSubmitting(true);
    try {
      await onSubmit({
        facilityId,
        dates: days,
        timeFrom,
        timeTo,
        sport: 'golf',
        minSpots,
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm p-6 space-y-5">
      <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">New Golf Preference</h3>

      {/* Course selector */}
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Course</label>
        <select
          value={facilityId}
          onChange={(e) => setFacilityId(e.target.value)}
          className="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2"
        >
          {GOLF_FACILITIES.map((f) => (
            <option key={f.id} value={f.id}>{f.displayName}</option>
          ))}
        </select>
      </div>

      {/* Days checkboxes */}
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Days</label>
        <div className="flex flex-wrap gap-2">
          {ALL_DAYS.map((day) => (
            <button
              key={day}
              type="button"
              onClick={() => toggleDay(day)}
              className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                days.includes(day)
                  ? 'bg-green-600 text-white'
                  : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
              }`}
            >
              {DAY_SHORT_LABELS[day]}
            </button>
          ))}
        </div>
        {days.length === 0 && (
          <p className="text-xs text-red-500 mt-1">Select at least one day</p>
        )}
      </div>

      {/* Time range */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">From</label>
          <input
            type="time"
            value={timeFrom}
            onChange={(e) => setTimeFrom(e.target.value)}
            className="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">To</label>
          <input
            type="time"
            value={timeTo}
            onChange={(e) => setTimeTo(e.target.value)}
            className="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2"
          />
        </div>
      </div>

      {/* Min spots */}
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Minimum available spots</label>
        <div className="flex gap-2">
          {[1, 2, 3, 4].map((n) => (
            <button
              key={n}
              type="button"
              onClick={() => setMinSpots(n)}
              className={`w-10 h-10 rounded-lg text-sm font-semibold transition-colors ${
                minSpots === n
                  ? 'bg-green-600 text-white'
                  : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
              }`}
            >
              {n}
            </button>
          ))}
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-3 pt-2">
        <button
          type="submit"
          disabled={submitting || days.length === 0}
          className="bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white font-medium py-2 px-5 rounded-lg transition-colors"
        >
          {submitting ? 'Saving...' : 'Save Preference'}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 font-medium py-2 px-4 transition-colors"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
