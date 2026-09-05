import type { CrossDomainAnomaly, CrossDomainSignal } from '../../api/types';
import { SeverityBadge } from '../common/Badge';

// Metrics where an operationally "worse" move is a DECREASE, so the arrow points down.
const DOWN_IS_WORSE = new Set([
  'valid_cost_km_coverage',
  'utilization',
  'utilization_change',
  'experience_rating',
  'experience_rating_change',
]);

const SHORT: Record<string, string> = {
  billing_change_pct: 'Billing',
  trip_volume_change_pct: 'Trips',
  valid_cost_km_coverage: 'Valid-km coverage',
  cost_per_valid_km: 'Cost/valid km',
  cost_per_valid_km_change: 'Cost/km',
  no_show_change: 'No-shows',
  no_show_rate: 'No-shows',
  utilization_change: 'Utilization',
  utilization: 'Utilization',
  safety_alert_rate_change: 'Safety alerts',
  safety_alerts_per_1000_trips: 'Safety alerts',
  delay_rate_change: 'Delay',
  experience_rating_change: 'Rating',
  zero_distance_billing_rate: 'Zero-distance bills',
  negative_distance_count: 'Negative distance',
  missing_join_count: 'Unmatched bills',
  late_10m_rate: 'Late >10m',
  late_5m_rate: 'Late >5m',
};

export function signalArrow(s: CrossDomainSignal): string {
  if (s.direction === 'stable') return '↔';
  const worseIsDown = DOWN_IS_WORSE.has(s.metric);
  if (s.direction === 'worse') return worseIsDown ? '↓' : '↑';
  return worseIsDown ? '↑' : '↓';
}

const TONE: Record<CrossDomainSignal['direction'], string> = {
  worse: 'bg-red-50 text-red-700 ring-red-200',
  better: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
  stable: 'bg-slate-100 text-slate-600 ring-slate-200',
};

export function SignalChip({ signal }: { signal: CrossDomainSignal }) {
  const label = SHORT[signal.metric] ?? signal.metric.replaceAll('_', ' ');
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium ring-1 ring-inset ${TONE[signal.direction]}`}
      title={signal.note ?? undefined}
    >
      {label} <span className="font-bold">{signalArrow(signal)}</span>
    </span>
  );
}

export function CrossSignalCard({
  item,
  onInvestigate,
}: {
  item: CrossDomainAnomaly;
  onInvestigate: (a: CrossDomainAnomaly) => void;
}) {
  return (
    <article className="card flex min-h-[210px] flex-col p-5">
      <div className="flex items-center justify-between">
        <SeverityBadge value={item.severity} />
        <span className="text-[11px] font-medium uppercase tracking-wide text-slate-400">
          {item.category.replaceAll('_', ' ')}
        </span>
      </div>
      <h3 className="mt-3 font-semibold text-navy">{item.title}</h3>
      <div className="text-sm text-slate-500">{item.entity_name}</div>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {item.signals.slice(0, 5).map((s, i) => (
          <SignalChip key={`${s.metric}-${i}`} signal={s} />
        ))}
      </div>
      <p className="mt-3 line-clamp-2 text-sm text-slate-600">{item.why_flagged}</p>
      <div className="mt-auto flex items-end justify-between pt-4">
        <div>
          <div className="text-lg font-semibold text-navy">
            {item.cross_signal_risk_score.toFixed(1)}
          </div>
          <div className="text-xs text-slate-500">
            cross-signal risk · {item.confidence} confidence
          </div>
        </div>
        <button onClick={() => onInvestigate(item)} className="btn-secondary py-1.5">
          Investigate
        </button>
      </div>
    </article>
  );
}
