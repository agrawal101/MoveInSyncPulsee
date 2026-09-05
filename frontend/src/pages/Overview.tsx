import { api } from '../api/client';
import type { Investigable } from '../api/types';
import { CrossSignalCard } from '../components/anomalies/CrossSignalCard';
import { DataHealth } from '../components/common/DataHealth';
import { ErrorState, Loading } from '../components/common/States';
import { KpiGrid } from '../components/metrics/KpiGrid';
import { useApi } from '../hooks/useApi';
import { baselineFor, monthLabel } from '../utils/format';

export function Overview({
  month,
  onInvestigate,
}: {
  month: string;
  onInvestigate: (a: Investigable) => void;
}) {
  const baseline = baselineFor(month);
  const overview = useApi(() => api.overview(month), [month]);
  const cross = useApi(() => api.crossDomain(month, baseline), [month, baseline]);
  const quality = useApi(() => api.quality(), []);
  const priorities = cross.data?.slice(0, 6) ?? [];

  return (
    <div className="space-y-7">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Mobility Command Center</h1>
        <p className="mt-1 text-slate-500">
          AI-detected operational priorities for {monthLabel(month)}
        </p>
      </header>

      {overview.loading ? (
        <Loading rows={1} />
      ) : overview.error ? (
        <ErrorState error={overview.error} retry={overview.retry} />
      ) : (
        overview.data && <KpiGrid data={overview.data} />
      )}

      <section>
        <div className="mb-4 flex items-end justify-between">
          <div>
            <div className="eyebrow text-blue-600">Agentic monitoring</div>
            <h2 className="section-title mt-1">Cross-Signal Intelligence</h2>
            <p className="mt-1 max-w-2xl text-sm text-slate-500">
              Anomalies detected by correlating mobility, safety, billing, employee and
              experience signals — patterns a single-metric report would miss.
            </p>
          </div>
          <div className="text-xs text-slate-500">
            Ranked by cross-signal risk, confidence, and sample protection
          </div>
        </div>
        {cross.loading ? (
          <Loading />
        ) : cross.error ? (
          <ErrorState error={cross.error} retry={cross.retry} />
        ) : priorities.length === 0 ? (
          <div className="card p-6 text-sm text-slate-500">
            No cross-domain anomalies cleared the deterministic thresholds for{' '}
            {monthLabel(month)}.
          </div>
        ) : (
          <div className="grid grid-cols-3 gap-4">
            {priorities.map((item) => (
              <CrossSignalCard key={item.id} item={item} onInvestigate={onInvestigate} />
            ))}
          </div>
        )}
      </section>

      {quality.loading ? (
        <Loading rows={1} />
      ) : quality.error ? (
        <ErrorState error={quality.error} retry={quality.retry} />
      ) : (
        quality.data && <DataHealth data={quality.data} />
      )}
    </div>
  );
}
