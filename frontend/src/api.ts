import axios from 'axios';
import type { Preference, PreferenceFormData } from './types';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'https://api.availabilitymonitor.club',
  headers: {
    'Content-Type': 'application/json',
  },
});

export async function registerUser(userId: string, name: string): Promise<void> {
  try {
    await api.post('/users', { userId, name });
  } catch (error: unknown) {
    if (axios.isAxiosError(error) && error.response?.status === 409) {
      // User already exists — treat as successful login
      return;
    }
    throw error;
  }
}

function normalizePreference(p: Record<string, unknown>): Preference {
  // Backwards compat: legacy items may have facilityIds array instead of facilityId string
  const facilityId = (p.facilityId as string | undefined)
    ?? ((p.facilityIds as string[] | undefined)?.[0] ?? '');
  // Backwards compat: legacy items may have "days" instead of "dates"
  const dates = (p.dates as string[] | undefined) ?? (p.days as string[] | undefined) ?? [];
  // Backwards compat: default sport to 'tennis' if missing (pre-multi-sport records)
  const sport = (p.sport as string | undefined) ?? 'tennis';
  return { ...p, facilityId, dates, sport } as unknown as Preference;
}

export async function getPreferences(userId: string): Promise<Preference[]> {
  const response = await api.get(`/users/${encodeURIComponent(userId)}/preferences`);
  const raw: Record<string, unknown>[] = response.data.data ?? response.data.preferences ?? response.data ?? [];
  return raw.map(normalizePreference);
}

export async function createPreference(
  userId: string,
  data: PreferenceFormData
): Promise<Preference> {
  const response = await api.post(
    `/users/${encodeURIComponent(userId)}/preferences`,
    data
  );
  return response.data.data ?? response.data;
}

export async function updatePreference(
  userId: string,
  preferenceId: string,
  data: PreferenceFormData
): Promise<Preference> {
  const response = await api.put(
    `/users/${encodeURIComponent(userId)}/preferences/${encodeURIComponent(preferenceId)}`,
    data
  );
  return response.data.data ?? response.data;
}

export async function deletePreference(
  userId: string,
  preferenceId: string
): Promise<void> {
  await api.delete(
    `/users/${encodeURIComponent(userId)}/preferences/${encodeURIComponent(preferenceId)}`
  );
}
