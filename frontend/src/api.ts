import axios from 'axios';
import type { Preference, PreferenceFormData } from './types';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'https://mk70fzrqy6.execute-api.eu-north-1.amazonaws.com/prod',
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

export async function getPreferences(userId: string): Promise<Preference[]> {
  const response = await api.get(`/users/${encodeURIComponent(userId)}/preferences`);
  return response.data.preferences ?? response.data ?? [];
}

export async function createPreference(
  userId: string,
  data: PreferenceFormData
): Promise<Preference> {
  const response = await api.post(
    `/users/${encodeURIComponent(userId)}/preferences`,
    data
  );
  return response.data;
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
  return response.data;
}

export async function deletePreference(
  userId: string,
  preferenceId: string
): Promise<void> {
  await api.delete(
    `/users/${encodeURIComponent(userId)}/preferences/${encodeURIComponent(preferenceId)}`
  );
}
