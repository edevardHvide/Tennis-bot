import { useState, useEffect, useCallback } from 'react';
import confetti from 'canvas-confetti';
import type { Preference, PreferenceFormData } from '../types';
import { getPreferences, createPreference, updatePreference, deletePreference } from '../api';
import PreferenceCard from './PreferenceCard';
import PreferenceForm from './PreferenceForm';
import FeatureRequestModal from './FeatureRequestModal';
import { useTheme } from '../useTheme';

interface DashboardProps {
  userId: string;
  onLogout: () => void;
}

export default function Dashboard({ userId, onLogout }: DashboardProps) {
  const [preferences, setPreferences] = useState<Preference[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<Preference | null>(null);
  const [showFeedback, setShowFeedback] = useState(false);
  const { dark, toggle } = useTheme();

  const fetchPreferences = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await getPreferences(userId);
      setPreferences(data);
    } catch {
      setError('Failed to load preferences. Please try again.');
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    fetchPreferences();
  }, [fetchPreferences]);

  const handleAdd = () => {
    setEditing(null);
    setShowForm(true);
  };

  const handleEdit = (preference: Preference) => {
    setEditing(preference);
    setShowForm(true);
  };

  const handleDelete = async (preferenceId: string) => {
    try {
      await deletePreference(userId, preferenceId);
      setPreferences((prev) => prev.filter((p) => p.preferenceId !== preferenceId));
    } catch {
      setError('Failed to delete preference.');
      setTimeout(() => setError(''), 4000);
    }
  };

  const handleFormSubmit = async (data: PreferenceFormData) => {
    // Strip facilityIds (form-only field) before sending to API
    const { facilityIds, ...apiData } = data;
    if (editing) {
      await updatePreference(userId, editing.preferenceId, apiData);
    } else {
      // Batch creation: create one preference per facility
      const facilities = facilityIds ?? [data.facilityId];
      for (const facilityId of facilities) {
        await createPreference(userId, { ...apiData, facilityId });
      }
    }
    const isNew = !editing;
    setShowForm(false);
    setEditing(null);
    await fetchPreferences();
    if (isNew) {
      confetti({ particleCount: 150, spread: 70, origin: { y: 0.6 } });
    }
  };

  const handleFormCancel = () => {
    setShowForm(false);
    setEditing(null);
  };

  return (
    <div
      className="min-h-screen bg-cover bg-center bg-fixed"
      style={{ backgroundImage: "url('/tennis-court.jpg')" }}
    >
      {/* Header */}
      <header className="bg-white/90 dark:bg-gray-900/90 backdrop-blur-sm border-b border-gray-200 dark:border-gray-700 shadow-sm">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <svg className="w-7 h-7 text-green-600 dark:text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
            <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100">🎾 Availability Monitor</h1>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={toggle}
              className="p-2 rounded-lg text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
              title={dark ? 'Switch to light mode' : 'Switch to dark mode'}
            >
              {dark ? (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                </svg>
              ) : (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
                </svg>
              )}
            </button>
            <span className="text-sm text-gray-600 dark:text-gray-400 hidden sm:inline">{userId}</span>
            <button
              onClick={onLogout}
              className="text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 font-medium transition-colors"
            >
              Logout
            </button>
          </div>
        </div>
      </header>

      {/* Content */}
      <main className="max-w-4xl mx-auto px-4 sm:px-6 py-8 bg-white/80 dark:bg-gray-900/80 backdrop-blur-sm min-h-[calc(100vh-65px)]">
        {/* Error banner */}
        {error && (
          <div className="mb-6 bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-400 text-sm px-4 py-3 rounded-lg border border-red-200 dark:border-red-800 flex items-center justify-between">
            <span>{error}</span>
            <button onClick={() => setError('')} className="text-red-500 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        )}

        {/* Title bar */}
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Your Preferences</h2>
          {!showForm && (
            <button
              onClick={handleAdd}
              className="bg-green-600 hover:bg-green-700 text-white font-medium py-2 px-4 rounded-lg transition-colors flex items-center gap-2"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4" />
              </svg>
              Add Preference
            </button>
          )}
        </div>

        {/* Form */}
        {showForm && (
          <div className="mb-8">
            <PreferenceForm
              editing={editing}
              onSubmit={handleFormSubmit}
              onCancel={handleFormCancel}
            />
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div className="flex justify-center py-16">
            <svg className="animate-spin h-8 w-8 text-green-600 dark:text-green-400" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          </div>
        )}

        {/* Onboarding guide — shown when user has no preferences */}
        {!loading && preferences.length === 0 && !showForm && (
          <div className="space-y-6">
            {/* Welcome */}
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm p-6 text-center">
              <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-green-100 dark:bg-green-900/50 mb-4">
                <svg className="w-7 h-7 text-green-600 dark:text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              </div>
              <h3 className="text-xl font-bold text-gray-900 dark:text-gray-100 mb-2">Welcome to Availability Monitor!</h3>
              <p className="text-gray-500 dark:text-gray-400 max-w-md mx-auto">
                Never miss an open court again. Availability Monitor watches{' '}
                <a href="https://www.matchi.se" target="_blank" rel="noopener noreferrer" className="text-green-600 dark:text-green-400 underline">matchi.se</a>{' '}
                for tennis and padel courts, and emails you when matching slots become available.
              </p>
            </div>

            {/* How it works — 3 steps */}
            <div className="grid gap-4 sm:grid-cols-3">
              <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm p-5">
                <div className="flex items-center gap-3 mb-3">
                  <span className="flex-shrink-0 w-8 h-8 rounded-full bg-green-600 text-white text-sm font-bold flex items-center justify-center">1</span>
                  <h4 className="font-semibold text-gray-900 dark:text-gray-100">Set a preference</h4>
                </div>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Pick a facility (e.g. Frogner), choose which days, and set your preferred time window.
                </p>
              </div>

              <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm p-5">
                <div className="flex items-center gap-3 mb-3">
                  <span className="flex-shrink-0 w-8 h-8 rounded-full bg-green-600 text-white text-sm font-bold flex items-center justify-center">2</span>
                  <h4 className="font-semibold text-gray-900 dark:text-gray-100">We scan for courts</h4>
                </div>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Every 5 minutes, we check matchi.se for newly available tennis and padel courts that match your criteria.
                </p>
              </div>

              <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm p-5">
                <div className="flex items-center gap-3 mb-3">
                  <span className="flex-shrink-0 w-8 h-8 rounded-full bg-green-600 text-white text-sm font-bold flex items-center justify-center">3</span>
                  <h4 className="font-semibold text-gray-900 dark:text-gray-100">Get notified</h4>
                </div>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  When a matching court opens up, you'll get an email alert so you can book it before it's gone.
                </p>
              </div>
            </div>

            {/* CTA */}
            <div className="text-center">
              <button
                onClick={handleAdd}
                className="bg-green-600 hover:bg-green-700 text-white font-semibold py-3 px-6 rounded-lg transition-colors text-lg"
              >
                Create Your First Preference
              </button>
            </div>
          </div>
        )}

        {/* Preferences grid */}
        {!loading && preferences.length > 0 && (
          <div className="grid gap-4 sm:grid-cols-2">
            {preferences.map((pref) => (
              <PreferenceCard
                key={pref.preferenceId}
                preference={pref}
                onEdit={handleEdit}
                onDelete={handleDelete}
              />
            ))}
          </div>
        )}

        {/* Feature request */}
        <div className="mt-12 pt-6 border-t border-gray-200 dark:border-gray-700 text-center">
          <button
            onClick={() => setShowFeedback(true)}
            className="text-sm text-gray-500 dark:text-gray-400 hover:text-green-600 dark:hover:text-green-400 transition-colors inline-flex items-center gap-1.5"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
            Have an idea? Submit a feature request
          </button>
        </div>

        {showFeedback && (
          <FeatureRequestModal
            userId={userId}
            onClose={() => setShowFeedback(false)}
          />
        )}
      </main>
    </div>
  );
}
