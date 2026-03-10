import { useState, useEffect, useCallback } from 'react';
import type { Preference, PreferenceFormData } from '../types';
import { getPreferences, createPreference, updatePreference, deletePreference } from '../api';
import PreferenceCard from './PreferenceCard';
import PreferenceForm from './PreferenceForm';

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
    setShowForm(false);
    setEditing(null);
    await fetchPreferences();
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
      <header className="bg-white/90 backdrop-blur-sm border-b border-gray-200 shadow-sm">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <svg className="w-7 h-7 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
            <h1 className="text-xl font-bold text-gray-900">Availability Monitor</h1>
          </div>
          <div className="flex items-center gap-4">
            <span className="text-sm text-gray-600 hidden sm:inline">{userId}</span>
            <button
              onClick={onLogout}
              className="text-sm text-gray-500 hover:text-gray-700 font-medium transition-colors"
            >
              Logout
            </button>
          </div>
        </div>
      </header>

      {/* Content */}
      <main className="max-w-4xl mx-auto px-4 sm:px-6 py-8 bg-white/80 backdrop-blur-sm min-h-[calc(100vh-65px)]">
        {/* Error banner */}
        {error && (
          <div className="mb-6 bg-red-50 text-red-700 text-sm px-4 py-3 rounded-lg border border-red-200 flex items-center justify-between">
            <span>{error}</span>
            <button onClick={() => setError('')} className="text-red-500 hover:text-red-700">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        )}

        {/* Title bar */}
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-2xl font-bold text-gray-900">Your Preferences</h2>
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
            <svg className="animate-spin h-8 w-8 text-green-600" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          </div>
        )}

        {/* Onboarding guide — shown when user has no preferences */}
        {!loading && preferences.length === 0 && !showForm && (
          <div className="space-y-6">
            {/* Welcome */}
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6 text-center">
              <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-green-100 mb-4">
                <svg className="w-7 h-7 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              </div>
              <h3 className="text-xl font-bold text-gray-900 mb-2">Welcome to Availability Monitor!</h3>
              <p className="text-gray-500 max-w-md mx-auto">
                Never miss an open court again. Availability Monitor watches{' '}
                <a href="https://www.matchi.se" target="_blank" rel="noopener noreferrer" className="text-green-600 underline">matchi.se</a>{' '}
                for tennis and padel courts, and emails you when matching slots become available.
              </p>
            </div>

            {/* How it works — 3 steps */}
            <div className="grid gap-4 sm:grid-cols-3">
              <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
                <div className="flex items-center gap-3 mb-3">
                  <span className="flex-shrink-0 w-8 h-8 rounded-full bg-green-600 text-white text-sm font-bold flex items-center justify-center">1</span>
                  <h4 className="font-semibold text-gray-900">Set a preference</h4>
                </div>
                <p className="text-sm text-gray-500">
                  Pick a facility (e.g. Frogner), choose which days, and set your preferred time window.
                </p>
              </div>

              <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
                <div className="flex items-center gap-3 mb-3">
                  <span className="flex-shrink-0 w-8 h-8 rounded-full bg-green-600 text-white text-sm font-bold flex items-center justify-center">2</span>
                  <h4 className="font-semibold text-gray-900">We scan for courts</h4>
                </div>
                <p className="text-sm text-gray-500">
                  Every 5 minutes, we check matchi.se for newly available tennis and padel courts that match your criteria.
                </p>
              </div>

              <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
                <div className="flex items-center gap-3 mb-3">
                  <span className="flex-shrink-0 w-8 h-8 rounded-full bg-green-600 text-white text-sm font-bold flex items-center justify-center">3</span>
                  <h4 className="font-semibold text-gray-900">Get notified</h4>
                </div>
                <p className="text-sm text-gray-500">
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
      </main>
    </div>
  );
}
