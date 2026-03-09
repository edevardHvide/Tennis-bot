export interface User {
  userId: string;
  name: string;
}

export interface Preference {
  preferenceId: string;
  userId: string;
  facilityId: string;
  dates: string[];
  timeFrom: string;
  timeTo: string;
}

export interface PreferenceFormData {
  facilityId: string;
  dates: string[];
  timeFrom: string;
  timeTo: string;
}

export interface Facility {
  id: string;
  displayName: string;
}

export const FACILITIES: Facility[] = [
  { id: 'frogner', displayName: 'Frogner' },
  { id: 'ota', displayName: 'OTA (Oslo Tennis Arena)' },
  { id: 'bergentennisarena', displayName: 'Bergen Tennis Arena' },
];

export function getFacilityDisplayName(facilityId: string): string {
  const facility = FACILITIES.find((f) => f.id === facilityId);
  return facility?.displayName ?? facilityId;
}
