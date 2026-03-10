import { useState, useEffect } from 'react';
import type { Preference, PreferenceFormData, Sport, CourtType, DayOfWeek } from '../types';
import { FACILITIES, ALL_DAYS, WEEKDAYS, WEEKENDS, DAY_SHORT_LABELS } from '../types';

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
  const [sport, setSport] = useState<Sport>(editing?.sport ?? 'tennis');
  const [courtType, setCourtType] = useState<CourtType | undefined>(editing?.courtType);
  const [facilityIds, setFacilityIds] = useState<string[]>(
    editing?.facilityId ? [editing.facilityId] : []
  );
  const [days, setDays] = useState<DayOfWeek[]>(
    (editing?.dates as DayOfWeek[]) ?? []
  );
  const [timeFrom, setTimeFrom] = useState(editing?.timeFrom ?? '');
  const [timeTo, setTimeTo] = useState(editing?.timeTo ?? '');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [submitError, setSubmitError] = useState('');

  const filteredFacilities = FACILITIES.filter((f) => f.sports.includes(sport));

  useEffect(() => {
    if (editing) {
      setSport(editing.sport ?? 'tennis');
      setCourtType(editing.courtType);
      setFacilityIds(editing.facilityId ? [editing.facilityId] : []);
      setDays((editing.dates as DayOfWeek[]) ?? []);
      setTimeFrom(editing.timeFrom);
      setTimeTo(editing.timeTo);
    }
  }, [editing]);

  const handleSportChange = (newSport: Sport) => {
    setSport(newSport);
    if (newSport === 'tennis') {
      setCourtType(undefined);
    }
    // Remove facilities that don't support the new sport
    setFacilityIds((prev) =>
      prev.filter((id) => {
        const facility = FACILITIES.find((f) => f.id === id);
        return facility?.sports.includes(newSport);
      })
    );
  };

  const toggleDay = (day: DayOfWeek) => {
    setDays((prev) =>
      prev.includes(day) ? prev.filter((d) => d !== day) : [...prev, day]
    );
    setErrors((prev) => {
      const { dates: _, ...rest } = prev;
      return rest;
    });
  };

  const selectDayGroup = (group: DayOfWeek[]) => {
    setDays((prev) => {
      const allSelected = group.every((d) => prev.includes(d));
      if (allSelected) {
        // Deselect the group
        return prev.filter((d) => !group.includes(d));
      }
      // Add all from group that aren't already selected
      const newDays = new Set([...prev, ...group]);
      return ALL_DAYS.filter((d) => newDays.has(d));
    });
    setErrors((prev) => {
      const { dates: _, ...rest } = prev;
      return rest;
    });
  };

  const selectAllDays = () => {
    const allSelected = ALL_DAYS.every((d) => days.includes(d));
    setDays(allSelected ? [] : [...ALL_DAYS]);
    setErrors((prev) => {
      const { dates: _, ...rest } = prev;
      return rest;
    });
  };

  const toggleFacility = (id: string) => {
    if (editing) {
      // When editing, only allow single facility (since each preference is one facility)
      setFacilityIds([id]);
    } else {
      setFacilityIds((prev) =>
        prev.includes(id) ? prev.filter((f) => f !== id) : [...prev, id]
      );
    }
    setErrors((prev) => {
      const { facilityId: _, ...rest } = prev;
      return rest;
    });
  };

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {};

    if (facilityIds.length === 0) newErrors.facilityId = 'Please select at least one facility.';
    else {
      const invalidFacility = facilityIds.find((id) => {
        const facility = FACILITIES.find((f) => f.id === id);
        return facility && !facility.sports.includes(sport);
      });
      if (invalidFacility) {
        newErrors.facilityId = 'A selected facility does not support this sport.';
      }
    }
    if (days.length === 0) newErrors.dates = 'Select at least one day.';
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
      // Sort days in canonical order
      const sortedDays = ALL_DAYS.filter((d) => days.includes(d));

      await onSubmit({
        facilityId: facilityIds[0],
        facilityIds,
        dates: sortedDays,
        timeFrom,
        timeTo,
        sport,
        ...(sport === 'padel' && courtType ? { courtType } : {}),
      });
    } catch {
      setSubmitError('Failed to save preference. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const accentColor = sport === 'tennis' ? 'green' : 'blue';

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
      <h2 className="text-xl font-semibold text-gray-900 mb-6">
        {editing ? 'Edit Preference' : 'Add New Preference'}
      </h2>

      <form onSubmit={handleSubmit} className="space-y-5">
        {/* Sport */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Sport
          </label>
          <div className="flex gap-3">
            <button
              type="button"
              onClick={() => handleSportChange('tennis')}
              disabled={loading}
              className={`flex-1 py-2.5 px-4 rounded-lg font-medium text-sm border transition-colors ${
                sport === 'tennis'
                  ? 'bg-green-600 text-white border-green-600'
                  : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
              }`}
            >
              Tennis
            </button>
            <button
              type="button"
              onClick={() => handleSportChange('padel')}
              disabled={loading}
              className={`flex-1 py-2.5 px-4 rounded-lg font-medium text-sm border transition-colors ${
                sport === 'padel'
                  ? 'bg-blue-600 text-white border-blue-600'
                  : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
              }`}
            >
              Padel
            </button>
          </div>
        </div>

        {/* Court Type (padel only) */}
        {sport === 'padel' && (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Court Type
            </label>
            <div className="flex gap-3">
              <button
                type="button"
                onClick={() => setCourtType(undefined)}
                disabled={loading}
                className={`flex-1 py-2 px-3 rounded-lg text-sm font-medium border transition-colors ${
                  courtType === undefined
                    ? 'bg-blue-600 text-white border-blue-600'
                    : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
                }`}
              >
                Any
              </button>
              <button
                type="button"
                onClick={() => setCourtType('double')}
                disabled={loading}
                className={`flex-1 py-2 px-3 rounded-lg text-sm font-medium border transition-colors ${
                  courtType === 'double'
                    ? 'bg-blue-600 text-white border-blue-600'
                    : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
                }`}
              >
                Double
              </button>
              <button
                type="button"
                onClick={() => setCourtType('single')}
                disabled={loading}
                className={`flex-1 py-2 px-3 rounded-lg text-sm font-medium border transition-colors ${
                  courtType === 'single'
                    ? 'bg-blue-600 text-white border-blue-600'
                    : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
                }`}
              >
                Single
              </button>
            </div>
          </div>
        )}

        {/* Facilities (checkboxes) */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            {editing ? 'Facility' : 'Facilities'}
          </label>
          <div className="space-y-2">
            {filteredFacilities.map((f) => (
              <label
                key={f.id}
                className={`flex items-center gap-3 px-4 py-2.5 rounded-lg border cursor-pointer transition-colors ${
                  facilityIds.includes(f.id)
                    ? accentColor === 'green'
                      ? 'bg-green-50 border-green-300'
                      : 'bg-blue-50 border-blue-300'
                    : 'bg-white border-gray-200 hover:bg-gray-50'
                } ${loading ? 'opacity-50 cursor-not-allowed' : ''}`}
              >
                <input
                  type={editing ? 'radio' : 'checkbox'}
                  checked={facilityIds.includes(f.id)}
                  onChange={() => toggleFacility(f.id)}
                  disabled={loading}
                  className={`h-4 w-4 rounded ${
                    accentColor === 'green'
                      ? 'text-green-600 focus:ring-green-500'
                      : 'text-blue-600 focus:ring-blue-500'
                  } border-gray-300`}
                />
                <span className="text-sm font-medium text-gray-800">{f.displayName}</span>
              </label>
            ))}
          </div>
          {!editing && facilityIds.length > 1 && (
            <p className="mt-1.5 text-xs text-gray-500">
              One preference will be created per facility.
            </p>
          )}
          {errors.facilityId && (
            <p className="mt-1 text-sm text-red-600">{errors.facilityId}</p>
          )}
        </div>

        {/* Days of Week */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Days
          </label>
          {/* Quick-select buttons */}
          <div className="flex gap-2 mb-2">
            <button
              type="button"
              onClick={() => selectDayGroup(WEEKDAYS)}
              disabled={loading}
              className={`text-xs font-medium px-3 py-1 rounded-full border transition-colors ${
                WEEKDAYS.every((d) => days.includes(d))
                  ? accentColor === 'green'
                    ? 'bg-green-100 text-green-700 border-green-300'
                    : 'bg-blue-100 text-blue-700 border-blue-300'
                  : 'bg-gray-50 text-gray-600 border-gray-200 hover:bg-gray-100'
              }`}
            >
              Weekdays
            </button>
            <button
              type="button"
              onClick={() => selectDayGroup(WEEKENDS)}
              disabled={loading}
              className={`text-xs font-medium px-3 py-1 rounded-full border transition-colors ${
                WEEKENDS.every((d) => days.includes(d))
                  ? accentColor === 'green'
                    ? 'bg-green-100 text-green-700 border-green-300'
                    : 'bg-blue-100 text-blue-700 border-blue-300'
                  : 'bg-gray-50 text-gray-600 border-gray-200 hover:bg-gray-100'
              }`}
            >
              Weekends
            </button>
            <button
              type="button"
              onClick={selectAllDays}
              disabled={loading}
              className={`text-xs font-medium px-3 py-1 rounded-full border transition-colors ${
                ALL_DAYS.every((d) => days.includes(d))
                  ? accentColor === 'green'
                    ? 'bg-green-100 text-green-700 border-green-300'
                    : 'bg-blue-100 text-blue-700 border-blue-300'
                  : 'bg-gray-50 text-gray-600 border-gray-200 hover:bg-gray-100'
              }`}
            >
              All
            </button>
          </div>
          {/* Day toggle buttons */}
          <div className="flex flex-wrap gap-1.5">
            {ALL_DAYS.map((day) => (
              <button
                key={day}
                type="button"
                onClick={() => toggleDay(day)}
                disabled={loading}
                className={`px-3 py-1.5 rounded-full text-sm font-medium border transition-colors ${
                  days.includes(day)
                    ? accentColor === 'green'
                      ? 'bg-green-600 text-white border-green-600'
                      : 'bg-blue-600 text-white border-blue-600'
                    : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
                }`}
              >
                {DAY_SHORT_LABELS[day]}
              </button>
            ))}
          </div>
          {errors.dates && (
            <p className="mt-1 text-sm text-red-600">{errors.dates}</p>
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
              className={`w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 ${
                accentColor === 'green'
                  ? 'focus:ring-green-500 focus:border-green-500'
                  : 'focus:ring-blue-500 focus:border-blue-500'
              } outline-none bg-white`}
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
              className={`w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 ${
                accentColor === 'green'
                  ? 'focus:ring-green-500 focus:border-green-500'
                  : 'focus:ring-blue-500 focus:border-blue-500'
              } outline-none bg-white`}
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
            className={`flex-1 ${
              accentColor === 'green'
                ? 'bg-green-600 hover:bg-green-700 disabled:bg-green-400'
                : 'bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400'
            } text-white font-medium py-2.5 px-4 rounded-lg transition-colors flex items-center justify-center`}
          >
            {loading ? (
              <svg className="animate-spin h-5 w-5 text-white" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
            ) : editing ? (
              'Update Preference'
            ) : facilityIds.length > 1 ? (
              `Add ${facilityIds.length} Preferences`
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
