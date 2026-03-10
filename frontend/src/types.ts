export type Sport = 'tennis' | 'padel';
export type CourtType = 'double' | 'single';

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
  sport: Sport;
  courtType?: CourtType;
}

export interface PreferenceFormData {
  facilityId: string;
  dates: string[];
  timeFrom: string;
  timeTo: string;
  sport: Sport;
  courtType?: CourtType;
}

export interface Facility {
  id: string;
  displayName: string;
  sports: string[];
}

export const FACILITIES: Facility[] = [
  { id: 'frogner', displayName: 'Frogner', sports: ['tennis'] },
  { id: 'ota', displayName: 'OTA (Oslo Tennis Arena)', sports: ['tennis', 'padel'] },
  { id: 'bergentennisarena', displayName: 'Bergen Tennis Arena', sports: ['tennis'] },
];

export function getFacilityDisplayName(facilityId: string): string {
  const facility = FACILITIES.find((f) => f.id === facilityId);
  return facility?.displayName ?? facilityId;
}
