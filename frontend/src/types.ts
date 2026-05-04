export type Sport = 'tennis' | 'padel' | 'golf';
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
  minSpots?: number;
}

export interface PreferenceFormData {
  facilityId: string;
  facilityIds?: string[]; // multi-facility form submission
  dates: string[]; // day-of-week names, e.g. ["monday", "friday"]
  timeFrom: string;
  timeTo: string;
  sport: Sport;
  courtType?: CourtType;
  minSpots?: number;
}

export interface Facility {
  id: string;
  displayName: string;
  sports: string[];
}

export const FACILITIES: Facility[] = [
  { id: 'ota', displayName: 'OTA (Oslo Tennis Arena)', sports: ['tennis', 'padel'] },
  { id: 'bergentennisarena', displayName: 'Bergen Tennis Arena', sports: ['tennis'] },
  { id: 'voldslokka', displayName: 'Voldsløkka', sports: ['tennis'] },
  { id: 'frogner', displayName: 'Frogner', sports: ['tennis'] },
  { id: 'furuset', displayName: 'Furuset', sports: ['tennis', 'padel'] },
  { id: 'interpadel', displayName: 'InterPadel Oslo', sports: ['padel'] },
  { id: 'nordicpadel', displayName: 'Nordic Padel', sports: ['padel'] },
  { id: 'nordstrand', displayName: 'Nordstrand Tennisklubb', sports: ['tennis'] },
  { id: 'bergenpadelklubb', displayName: 'Bergen Padelklubb', sports: ['padel'] },
  { id: 'interpadelbergen', displayName: 'InterPadel Bergen (Sandsli)', sports: ['padel'] },
  { id: 'harvard', displayName: 'Harvard Recreation', sports: ['tennis'] },
  { id: 'onsoy', displayName: 'Onsøy Golf', sports: ['golf'] },
  { id: 'haga', displayName: 'Haga GK', sports: ['golf'] },
  { id: 'grini', displayName: 'Grini GK', sports: ['golf'] },
  { id: 'losby', displayName: 'Losby Golfklubb', sports: ['golf'] },
  { id: 'rivertz', displayName: "Padelbane Arkitekt Rivertz' plass", sports: ['padel'] },
];

export interface HighscoreEntry {
  scoreId: string;
  userId: string;
  playerName: string;
  score: number;
  createdAt: string;
}

export interface AvailabilitySlot {
  facilityId: string;
  sport: Sport;
  timeSlot: string;
  courtName: string;
}

export interface AvailabilityDay {
  date: string;
  weekday: DayOfWeek;
  slots: AvailabilitySlot[];
}

export interface FacilityInfo {
  facilityId: string;
  displayName: string;
}

export interface AvailabilityResponse {
  days: AvailabilityDay[];
  facilities: FacilityInfo[];
  freshness: Record<string, { updatedAt: string }>;
  nextUpdateAt: string;
  generatedAt: string;
}

// ── Festival ticket monitoring (beta) ────────────────────────────────────────

export interface Festival {
  festivalId: string;
  name: string;
  dates: string;
  location: string;
  platform: string;
  ticketAvailable: boolean | null;
  ticketStatusText: string;
  lastCheckedAt: string | null;
  url: string;
}

export interface FestivalSubscription {
  festivalId: string;
  enabled: boolean;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

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
