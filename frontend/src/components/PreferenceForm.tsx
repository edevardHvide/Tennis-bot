import { useState, useEffect } from 'react';
import type { Preference, PreferenceFormData } from '../types';
import { FACILITIES } from '../types';

interface PreferenceFormProps {
  editing: Preference | null;
  onSubmit: (data: PreferenceFormData) => Promise<void>;
  onCancel: () => void;
}

function generateTimeOptions(): string[] {
  const options: string[] = [];
  for (let h = 6; h <= 23; h++) {
    options.push(`${String(h).padStart(2, '0')}:00`);
    if (h < 23) {
      options.push(`${String(h).padStart(2, '0')}:30`);
    }
  }
  return options;
}

const TIME_OPTIONS = generateTimeOptions();

export default function PreferenceForm({ editing, onSubmit, onCancel }: PreferenceFormProps) {
  const [facilityId, setFacilityId] = useState(editing?.facilityId ?? '');
  const [dates, setDates] = useState<string[]>(editing?.dates ?? []);
  const [dateInput, setDateInput] = useState('');
  const [timeFrom, setTimeFrom] = useState(editing?.timeFrom ?? '');
  const [timeTo, setTimeTo] = useState(editing?.timeTo ?? '');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [submitError, setSubmitError] = useState('');

  useEffect(() => {
    if (editing) {
      setFacilityId(editing.facilityId);
      setDates([...editing.dates]);
      setTimeFrom(editing.timeFrom);
      setTimeTo(editing.timeTo);
    }
  }, [editing]);

  const addDate = () => {
    if (!dateInput) return;
    if (dates.includes(dateInput)) {
      setErrors((prev) => ({ ...prev, dates: 'Date already added.' }));
      return;
    }
    setDates((prev) => [...prev, dateInput].sort());
    setDateInput('');
    setErrors((prev) => {
      const { dates: _, ...rest } = prev;
      return rest;
    });
  };

  const removeDate = (date: string) => {
    setDates((prev) => prev.filter((d) => d !== date));
  };

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {};

    if (!facilityId) newErrors.facilityId = 'Please select a facility.';
    if (dates.length === 0) newErrors.dates = 'Add at least one date.';
    if (!timeFrom) newErrors.timeFrom = 'Select a start time.';
    if (!timeTo) newErrors.timeTo = 'Select an end time.';
    if (timeFrom && timeTo && timeFrom >= timeTo) {
      newErrors.timeTo = 'End time must be after start time.';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitError('');
    if (!validate()) return;

    setLoading(true);
    try {
      await onSubmit({ facilityId, dates, timeFrom, timeTo });
    } catch {
      setSubmitError('Failed to save preference. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
      <h2 className="text-xl font-semibold text-gray-900 mb-6">
        {editing ? 'Edit Preference' : 'Add New Preference'}
      </h2>

      <form onSubmit={handleSubmit} className="space-y-5">
        {/* Facility */}
        <div>
          <label htmlFor="facility" className="block text-sm font-medium text-gray-700 mb-1">
            Facility
          </label>
          <select
            id="facility"
            value={facilityId}
            onChange={(e) => setFacilityId(e.target.value)}
            className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500 focus:border-green-500 outline-none bg-white"
            disabled={loading}
          >
            <option value="">Select a facility...</option>
            {FACILITIES.map((f) => (
              <option key={f.id} value={f.id}>
                {f.displayName}
              </option>
            ))}
          </select>
          {errors.facilityId && (
            <p className="mt-1 text-sm text-red-600">{errors.facilityId}</p>
          )}
        </div>

        {/* Dates */}
        <div>
          <label htmlFor="date-input" className="block text-sm font-medium text-gray-700 mb-1">
            Dates
          </label>
          <div className="flex gap-2">
            <input
              id="date-input"
              type="date"
              value={dateInput}
              onChange={(e) => setDateInput(e.target.value)}
              className="flex-1 px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500 focus:border-green-500 outline-none"
              disabled={loading}
            />
            <button
              type="button"
              onClick={addDate}
              disabled={loading || !dateInput}
              className="px-4 py-2.5 bg-green-600 hover:bg-green-700 disabled:bg-gray-300 text-white font-medium rounded-lg transition-colors"
            >
              Add
            </button>
          </div>
          {errors.dates && (
            <p className="mt-1 text-sm text-red-600">{errors.dates}</p>
          )}
          {dates.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-2">
              {dates.map((date) => (
                <span
                  key={date}
                  className="inline-flex items-center gap-1 bg-green-50 text-green-700 text-sm font-medium px-3 py-1 rounded-full border border-green-200"
                >
                  {date}
                  <button
                    type="button"
                    onClick={() => removeDate(date)}
                    className="text-green-500 hover:text-red-500 transition-colors"
                    disabled={loading}
                  >
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Time Range */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label htmlFor="time-from" className="block text-sm font-medium text-gray-700 mb-1">
              From
            </label>
            <select
              id="time-from"
              value={timeFrom}
              onChange={(e) => setTimeFrom(e.target.value)}
              className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500 focus:border-green-500 outline-none bg-white"
              disabled={loading}
            >
              <option value="">Start time...</option>
              {TIME_OPTIONS.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            {errors.timeFrom && (
              <p className="mt-1 text-sm text-red-600">{errors.timeFrom}</p>
            )}
          </div>
          <div>
            <label htmlFor="time-to" className="block text-sm font-medium text-gray-700 mb-1">
              To
            </label>
            <select
              id="time-to"
              value={timeTo}
              onChange={(e) => setTimeTo(e.target.value)}
              className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500 focus:border-green-500 outline-none bg-white"
              disabled={loading}
            >
              <option value="">End time...</option>
              {TIME_OPTIONS.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            {errors.timeTo && (
              <p className="mt-1 text-sm text-red-600">{errors.timeTo}</p>
            )}
          </div>
        </div>

        {submitError && (
          <div className="bg-red-50 text-red-700 text-sm px-4 py-3 rounded-lg border border-red-200">
            {submitError}
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-3 pt-2">
          <button
            type="submit"
            disabled={loading}
            className="flex-1 bg-green-600 hover:bg-green-700 disabled:bg-green-400 text-white font-medium py-2.5 px-4 rounded-lg transition-colors flex items-center justify-center"
          >
            {loading ? (
              <svg className="animate-spin h-5 w-5 text-white" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
            ) : editing ? (
              'Update Preference'
            ) : (
              'Add Preference'
            )}
          </button>
          <button
            type="button"
            onClick={onCancel}
            disabled={loading}
            className="px-6 py-2.5 border border-gray-300 text-gray-700 font-medium rounded-lg hover:bg-gray-50 transition-colors"
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}
