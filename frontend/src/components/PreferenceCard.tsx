import { useState } from 'react';
import type { Preference } from '../types';
import { getFacilityDisplayName, formatDays } from '../types';

interface PreferenceCardProps {
  preference: Preference;
  onEdit: (preference: Preference) => void;
  onDelete: (preferenceId: string) => void;
}

export default function PreferenceCard({ preference, onEdit, onDelete }: PreferenceCardProps) {
  const [deleting, setDeleting] = useState(false);

  const handleDelete = async () => {
    if (!confirm('Delete this preference?')) return;
    setDeleting(true);
    try {
      await onDelete(preference.preferenceId);
    } finally {
      setDeleting(false);
    }
  };

  const sport = preference.sport ?? 'tennis';
  const daysLabel = formatDays(preference.dates);

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between mb-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <h3 className="text-lg font-semibold text-gray-900">
              {getFacilityDisplayName(preference.facilityId)}
            </h3>
            <span
              className={`inline-flex items-center text-xs font-medium px-2 py-0.5 rounded-full ${
                sport === 'tennis'
                  ? 'bg-green-100 text-green-700 border border-green-200'
                  : 'bg-blue-100 text-blue-700 border border-blue-200'
              }`}
            >
              {sport === 'tennis' ? 'Tennis' : 'Padel'}
            </span>
            {preference.courtType && (
              <span className="inline-flex items-center text-xs font-medium px-2 py-0.5 rounded-full bg-gray-100 text-gray-600 border border-gray-200">
                {preference.courtType === 'double' ? 'Double' : 'Single'}
              </span>
            )}
          </div>
          <p className="text-sm text-green-600 font-medium">
            {preference.timeFrom} - {preference.timeTo}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => onEdit(preference)}
            className="text-gray-400 hover:text-green-600 transition-colors p-1"
            title="Edit"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
            </svg>
          </button>
          <button
            onClick={handleDelete}
            disabled={deleting}
            className="text-gray-400 hover:text-red-600 disabled:text-gray-300 transition-colors p-1"
            title="Delete"
          >
            {deleting ? (
              <svg className="animate-spin w-5 h-5" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
            ) : (
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
            )}
          </button>
        </div>
      </div>

      <div>
        <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">Days</p>
        <span
          className={`inline-block text-xs font-medium px-2.5 py-1 rounded-full border ${
            sport === 'tennis'
              ? 'bg-green-50 text-green-700 border-green-200'
              : 'bg-blue-50 text-blue-700 border-blue-200'
          }`}
        >
          {daysLabel}
        </span>
      </div>
    </div>
  );
}
