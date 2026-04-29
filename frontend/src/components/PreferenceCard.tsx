import { useState } from 'react';
import type { Preference } from '../types';
import { getFacilityDisplayName, formatDays } from '../types';
import SnakeGame from './SnakeGame';

interface PreferenceCardProps {
  preference: Preference;
  userId: string;
  onEdit: (preference: Preference) => void;
  onDelete: (preferenceId: string) => void;
}

export default function PreferenceCard({ preference, userId, onEdit, onDelete }: PreferenceCardProps) {
  const [deleting, setDeleting] = useState(false);
  const [showGame, setShowGame] = useState(false);

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

  const sportBadgeClass =
    sport === 'tennis'
      ? 'bg-green-100 dark:bg-green-900/50 text-green-700 dark:text-green-400 border border-green-200 dark:border-green-800'
      : sport === 'padel'
      ? 'bg-blue-100 dark:bg-blue-900/50 text-blue-700 dark:text-blue-400 border border-blue-200 dark:border-blue-800'
      : 'bg-amber-100 dark:bg-amber-900/50 text-amber-700 dark:text-amber-400 border border-amber-200 dark:border-amber-800';

  const sportLabel = sport === 'tennis' ? 'Tennis' : sport === 'padel' ? 'Padel' : 'Golf';

  const daysBadgeClass =
    sport === 'tennis'
      ? 'bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-400 border-green-200 dark:border-green-800'
      : sport === 'padel'
      ? 'bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400 border-blue-200 dark:border-blue-800'
      : 'bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-800';

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between mb-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              {getFacilityDisplayName(preference.facilityId)}
            </h3>
            <span className={`inline-flex items-center text-xs font-medium px-2 py-0.5 rounded-full ${sportBadgeClass}`}>
              {sportLabel}
            </span>
            {preference.courtType && (
              <span className="inline-flex items-center text-xs font-medium px-2 py-0.5 rounded-full bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 border border-gray-200 dark:border-gray-600">
                {preference.courtType === 'double' ? 'Double' : 'Single'}
              </span>
            )}
          </div>
          <p className="text-sm text-green-600 dark:text-green-400 font-medium">
            {preference.timeFrom} - {preference.timeTo}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={(e) => { e.stopPropagation(); setShowGame(true); }}
            className="text-gray-400 hover:text-green-600 dark:hover:text-green-400 transition-colors p-1"
            title="Play Snake"
          >
            <span className="text-base leading-none">🐍</span>
          </button>
          <button
            onClick={() => onEdit(preference)}
            className="text-gray-400 hover:text-green-600 dark:hover:text-green-400 transition-colors p-1"
            title="Edit"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
            </svg>
          </button>
          <button
            onClick={handleDelete}
            disabled={deleting}
            className="text-gray-400 hover:text-red-600 dark:hover:text-red-400 disabled:text-gray-300 dark:disabled:text-gray-600 transition-colors p-1"
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
        <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-2">Days</p>
        <span className={`inline-block text-xs font-medium px-2.5 py-1 rounded-full border ${daysBadgeClass}`}>
          {daysLabel}
        </span>
      </div>

      {showGame && (
        <SnakeGame userId={userId} onClose={() => setShowGame(false)} />
      )}
    </div>
  );
}
