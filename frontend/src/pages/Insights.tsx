import { useState } from 'react';
import { api } from '../api/client';
import type { CrossDomainCategory, Investigable } from '../api/types';
import { CrossSignalCard } from '../components/anomalies/CrossSignalCard';
import { ErrorState, Loading } from '../components/common/States';
import { useApi } from '../hooks/useApi';
import { baselineFor } from '../utils/format';

const FILTERS: { label: string; value: CrossDomainCategory | 'all' }[] = [
  { label: 'All', value: 'all' },
  { label: 'Billing Integrity', value: 'billing_integrity' },
  { label: 'Safety', value: 'safety_pattern' },
  { label: 'Vendor Performance', value: 'vendor_operational_divergence' },
  { label: 'Shift Readiness', value: 'shift_readiness_pattern' },
  { label: 'Data Integrity', value: 'data_integrity_anomaly' },
];

export function Insights({
  month,
  onInvestigate,
}: {
  month: string;
  onInvestigate: (a: Investigable) => void;
}) {
  const [filter, setFilter] = useState<CrossDomainCategory | 'all'>('all');
  const baseline = baselineFor(month);
  const state = useApi(() => api.crossDomain(month, baseline, undefined, '50'), [month, baseline]);
  const items = (state.data ?? []).filter((a) => filter === 'all' || a.category === filter);

  return (
    <div>
      <header className="mb-5">
        <h1 className="text-2xl font-semibold">Cross-Signal Intelligence</h1>
        <p className="mt-1 text-slate-500">
          Suspicious multi-signal combinations correlated across billing, safety, service,
          shift and data-quality domains.
        </p>
      </header>

      <div className="mb-6 flex flex-wrap gap-2">
        {FILTERS.map((f) => {
          const count =
            f.value === 'all'
              ? state.data?.length ?? 0
              : state.data?.filter((a) => a.category === f.value).length ?? 0;
          return (
            <button
              key={f.value}
              onClick={() => setFilter(f.value)}
              className={`rounded-full px-3.5 py-1.5 text-sm font-medium ring-1 ring-inset transition ${
                filter === f.value
                  ? 'bg-blue-600 text-white ring-blue-600'
                  : 'bg-white text-slate-600 ring-slate-200 hover:bg-slate-50'
              }`}
            >
              {f.label}
              <span className={filter === f.value ? 'ml-1.5 text-blue-100' : 'ml-1.5 text-slate-400'}>
                {count}
              </span>
            </button>
          );
        })}
      </div>

      {state.loading ? (
        <Loading rows={5} />
      ) : state.error ? (
        <ErrorState error={state.error} retry={state.retry} />
      ) : items.length === 0 ? (
        <div className="card p-6 text-sm text-slate-500">No anomalies for this filter.</div>
      ) : (
        <div className="grid grid-cols-3 gap-4">
          {items.map((a) => (
            <CrossSignalCard key={a.id} item={a} onInvestigate={onInvestigate} />
          ))}
        </div>
      )}
    </div>
  );
}
