export type Sport = 'tennis' | 'padel';
export type CourtType = 'double' | 'single';
export type DayOfWeek =
  | 'monday'
  | 'tuesday'
  | 'wednesday'
  | 'thursday'
  | 'friday'
  | 'saturday'
  | 'sunday';

export const ALL_DAYS: DayOfWeek[] = [
  'monday',
  'tuesday',
  'wednesday',
  'thursday',
  'friday',
  'saturday',
  'sunday',
];

export const WEEKDAYS: DayOfWeek[] = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday'];
export const WEEKENDS: DayOfWeek[] = ['saturday', 'sunday'];

export const DAY_SHORT_LABELS: Record<DayOfWeek, string> = {
  monday: 'Mon',
  tuesday: 'Tue',
  wednesday: 'Wed',
  thursday: 'Thu',
  friday: 'Fri',
  saturday: 'Sat',
  sunday: 'Sun',
};

export interface User {
  userId: string;
  name: string;
}

export interface Preference {
  preferenceId: string;
  userId: string;
  facilityId: string;
  dates: string[]; // day-of-week names, e.g. ["monday", "friday"]
  timeFrom: string;
  timeTo: string;
  sport: Sport;
  courtType?: CourtType;
}

export interface PreferenceFormData {
  facilityId: string;
  facilityIds?: string[]; // multi-facility form submission
  dates: string[]; // day-of-week names, e.g. ["monday", "friday"]
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
  { id: 'voldslokka', displayName: 'Voldsløkka', sports: ['tennis'] },
  { id: 'furuset', displayName: 'Furuset', sports: ['tennis', 'padel'] },
  { id: 'interpadel', displayName: 'InterPadel Oslo', sports: ['padel'] },
  { id: 'nordicpadel', displayName: 'Nordic Padel', sports: ['padel'] },
  { id: 'ullern', displayName: 'Ullern Tennisklubb', sports: ['tennis'] },
  { id: 'nordstrand', displayName: 'Nordstrand Tennisklubb', sports: ['tennis'] },
  { id: 'heming', displayName: 'Heming Tennis og Padel', sports: ['tennis', 'padel'] },
  { id: 'holmenkollen', displayName: 'Holmenkollen Tennisklubb', sports: ['tennis'] },
];

export function getFacilityDisplayName(facilityId: string): string {
  const facility = FACILITIES.find((f) => f.id === facilityId);
  return facility?.displayName ?? facilityId;
}

/**
 * Format an array of day-of-week strings for display.
 * Detects patterns: "Weekdays", "Weekends", "Every day", or lists individual days.
 */
export function formatDays(days: string[]): string {
  const daySet = new Set(days.map((d) => d.toLowerCase()));

  const hasAllWeekdays = WEEKDAYS.every((d) => daySet.has(d));
  const hasAllWeekends = WEEKENDS.every((d) => daySet.has(d));

  if (hasAllWeekdays && hasAllWeekends) return 'Every day';
  if (hasAllWeekdays && daySet.size === 5) return 'Weekdays';
  if (hasAllWeekends && daySet.size === 2) return 'Weekends';

  // List individual days in order
  return ALL_DAYS.filter((d) => daySet.has(d))
    .map((d) => DAY_SHORT_LABELS[d])
    .join(', ');
}
