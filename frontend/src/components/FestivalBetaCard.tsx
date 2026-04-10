import { useState, useEffect } from 'react';
import type { Festival, FestivalSubscription } from '../types';
import { getFestivals, getFestivalSubscriptions, toggleFestivalSubscription } from '../api';

interface FestivalBetaCardProps {
  userId: string;
}

export default function FestivalBetaCard({ userId }: FestivalBetaCardProps) {
  const [festivals, setFestivals] = useState<Festival[]>([]);
  const [subscriptions, setSubscriptions] = useState<Record<string, boolean>>({});
  const [expanded, setExpanded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [toggling, setToggling] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!expanded) return;
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [festData, subData] = await Promise.all([
          getFestivals(),
          getFestivalSubscriptions(userId),
        ]);
        if (cancelled) return;
        setFestivals(festData);
        const subMap: Record<string, boolean> = {};
        subData.forEach((s: FestivalSubscription) => {
          subMap[s.festivalId] = s.enabled;
        });
        setSubscriptions(subMap);
      } catch {
        if (!cancelled) setError('Could not load festivals');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => { cancelled = true; };
  }, [expanded, userId]);

  async function handleToggle(festivalId: string) {
    const newEnabled = !subscriptions[festivalId];
    setToggling(festivalId);
    setSubscriptions((prev) => ({ ...prev, [festivalId]: newEnabled }));
    try {
      await toggleFestivalSubscription(userId, festivalId, newEnabled);
    } catch {
      // Revert on failure
      setSubscriptions((prev) => ({ ...prev, [festivalId]: !newEnabled }));
    } finally {
      setToggling(null);
    }
  }

  function formatLastChecked(iso: string | null): string {
    if (!iso) return 'Never';
    const d = new Date(iso);
    const now = new Date();
    const diffMin = Math.floor((now.getTime() - d.getTime()) / 60000);
    if (diffMin < 1) return 'Just now';
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffH = Math.floor(diffMin / 60);
    if (diffH < 24) return `${diffH}h ago`;
    return d.toLocaleDateString('nb-NO', { day: 'numeric', month: 'short' });
  }

  return (
    <div className="mt-8">
      {/* Collapsed: teaser button */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full group"
      >
        <div className={`
          relative overflow-hidden rounded-xl border transition-all duration-300
          ${expanded
            ? 'border-amber-300 dark:border-amber-600 bg-gradient-to-br from-amber-50 via-orange-50 to-amber-50 dark:from-amber-950/40 dark:via-orange-950/30 dark:to-amber-950/40 shadow-md'
            : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 hover:border-amber-300 dark:hover:border-amber-700 hover:shadow-md'
          }
          p-5
        `}>
          {/* Subtle background pattern */}
          <div className="absolute inset-0 opacity-[0.03] dark:opacity-[0.05]"
            style={{
              backgroundImage: `url("data:image/svg+xml,%3Csvg width='20' height='20' viewBox='0 0 20 20' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M10 2l2.5 5.5L18 9l-4 4 1 5.5L10 15.5 4.5 18.5l1-5.5-4-4 5.5-1.5z' fill='%23f59e0b' fill-opacity='1'/%3E%3C/svg%3E")`,
              backgroundSize: '40px 40px',
            }}
          />

          <div className="relative flex items-center justify-between">
            <div className="flex items-center gap-3">
              {/* Ticket icon */}
              <div className={`
                flex items-center justify-center w-10 h-10 rounded-lg transition-colors
                ${expanded
                  ? 'bg-amber-200/60 dark:bg-amber-800/40'
                  : 'bg-gray-100 dark:bg-gray-700 group-hover:bg-amber-100 dark:group-hover:bg-amber-900/30'
                }
              `}>
                <svg className={`w-5 h-5 transition-colors ${expanded ? 'text-amber-600 dark:text-amber-400' : 'text-gray-500 dark:text-gray-400 group-hover:text-amber-600 dark:group-hover:text-amber-400'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="1.5">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 6v.75m0 3v.75m0 3v.75m0 3V18m-9-5.25h5.25M7.5 15h3M3.375 5.25c-.621 0-1.125.504-1.125 1.125v3.026a2.999 2.999 0 010 5.198v3.026c0 .621.504 1.125 1.125 1.125h17.25c.621 0 1.125-.504 1.125-1.125v-3.026a2.999 2.999 0 010-5.198V6.375c0-.621-.504-1.125-1.125-1.125H3.375z" />
                </svg>
              </div>

              <div className="text-left">
                <div className="flex items-center gap-2">
                  <span className={`font-semibold transition-colors ${expanded ? 'text-gray-900 dark:text-gray-100' : 'text-gray-700 dark:text-gray-300 group-hover:text-gray-900 dark:group-hover:text-gray-100'}`}>
                    Festival Ticket Alerts
                  </span>
                  <span className="inline-flex items-center text-[10px] font-bold tracking-wider uppercase px-1.5 py-0.5 rounded bg-amber-200 dark:bg-amber-800 text-amber-800 dark:text-amber-200 border border-amber-300 dark:border-amber-700">
                    Beta
                  </span>
                </div>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                  Get notified when resale tickets appear
                </p>
              </div>
            </div>

            {/* Chevron */}
            <svg
              className={`w-5 h-5 text-gray-400 transition-transform duration-300 ${expanded ? 'rotate-180' : ''}`}
              fill="none" stroke="currentColor" viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" />
            </svg>
          </div>
        </div>
      </button>

      {/* Expanded: festival list */}
      <div className={`
        overflow-hidden transition-all duration-300 ease-in-out
        ${expanded ? 'max-h-[600px] opacity-100 mt-3' : 'max-h-0 opacity-0'}
      `}>
        <div className="rounded-xl border border-amber-200 dark:border-amber-800/50 bg-white dark:bg-gray-800 overflow-hidden">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <svg className="animate-spin w-5 h-5 text-amber-500" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
            </div>
          ) : error ? (
            <div className="px-5 py-4 text-sm text-red-600 dark:text-red-400">{error}</div>
          ) : festivals.length === 0 ? (
            <div className="px-5 py-6 text-sm text-gray-500 dark:text-gray-400 text-center">
              No festivals available for monitoring yet.
            </div>
          ) : (
            <div className="divide-y divide-gray-100 dark:divide-gray-700/50">
              {festivals.map((festival) => {
                const isEnabled = subscriptions[festival.festivalId] ?? false;
                const isToggling = toggling === festival.festivalId;
                const isSoldOut = festival.ticketAvailable === false;
                const isAvailable = festival.ticketAvailable === true;

                return (
                  <div
                    key={festival.festivalId}
                    className="px-5 py-4 flex items-center gap-4"
                  >
                    {/* Festival info */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-medium text-gray-900 dark:text-gray-100 text-sm">
                          {festival.name}
                        </span>
                        {/* Status badge */}
                        {isSoldOut && (
                          <span className="inline-flex items-center text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-400 border border-red-200 dark:border-red-800">
                            Sold out
                          </span>
                        )}
                        {isAvailable && (
                          <span className="inline-flex items-center text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800 animate-pulse">
                            Tickets available!
                          </span>
                        )}
                        {festival.ticketAvailable === null && (
                          <span className="inline-flex items-center text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400">
                            Checking...
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-3 mt-1 text-xs text-gray-500 dark:text-gray-400">
                        <span>{festival.dates}</span>
                        <span className="text-gray-300 dark:text-gray-600">·</span>
                        <span>{festival.location}</span>
                        {festival.lastCheckedAt && (
                          <>
                            <span className="text-gray-300 dark:text-gray-600">·</span>
                            <span>Checked {formatLastChecked(festival.lastCheckedAt)}</span>
                          </>
                        )}
                      </div>
                    </div>

                    {/* External link */}
                    <a
                      href={festival.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex-shrink-0 p-1.5 text-gray-400 hover:text-amber-600 dark:hover:text-amber-400 transition-colors"
                      title="Open ticket page"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                      </svg>
                    </a>

                    {/* Toggle */}
                    <button
                      onClick={() => handleToggle(festival.festivalId)}
                      disabled={isToggling}
                      className={`
                        relative flex-shrink-0 w-11 h-6 rounded-full transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-amber-400 focus:ring-offset-2 dark:focus:ring-offset-gray-800
                        ${isEnabled
                          ? 'bg-amber-500 dark:bg-amber-600'
                          : 'bg-gray-200 dark:bg-gray-600'
                        }
                        ${isToggling ? 'opacity-50 cursor-wait' : 'cursor-pointer'}
                      `}
                      title={isEnabled ? 'Disable alerts' : 'Enable alerts'}
                    >
                      <span
                        className={`
                          inline-block w-4 h-4 bg-white rounded-full shadow transform transition-transform duration-200 mt-1
                          ${isEnabled ? 'translate-x-6' : 'translate-x-1'}
                        `}
                      />
                    </button>
                  </div>
                );
              })}
            </div>
          )}

          {/* Footer hint */}
          {festivals.length > 0 && !loading && (
            <div className="px-5 py-3 bg-amber-50/50 dark:bg-amber-950/20 border-t border-amber-100 dark:border-amber-900/30">
              <p className="text-[11px] text-amber-700/70 dark:text-amber-400/60">
                We check for resale tickets every 15 minutes. You'll get an email the moment tickets appear.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
