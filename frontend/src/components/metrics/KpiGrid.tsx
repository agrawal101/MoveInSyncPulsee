import type { Overview } from '../../api/types';
import { metricValue } from '../../utils/format';

const cards = [
  ['total_trips', 'Total Trips'],
  ['delay_rate', 'Delay Rate'],
  ['no_show_rate', 'No-show Rate'],
  ['alerts_per_1000_trips', 'Safety Alerts / 1,000'],
  ['total_billing_amount', 'Billing'],
  ['ev_share', 'EV Share'],
] as const;

function trendColor(key: string, change: number | null | undefined): string {
  if (change == null) return 'text-slate-400';
  if (key === 'delay_rate' || key === 'no_show_rate' || key === 'alerts_per_1000_trips') {
    return change < 0 ? 'text-emerald-600' : 'text-red-600';
  }
  if (key === 'ev_share') return change > 0 ? 'text-emerald-600' : 'text-amber-600';
  return 'text-blue-600';
}

export function KpiGrid({ data }: { data: Overview }) {
  return (
    <div className="grid grid-cols-3 gap-4 xl:grid-cols-6">
      {cards.map(([key, label]) => {
        const metric = data.metrics[key];
        const change = metric?.relative_change_pct;
        return (
          <article className="card p-4" key={key}>
            <div className="text-xs font-medium text-slate-500">{label}</div>
            <div className="mt-2 text-2xl font-semibold tracking-tight text-navy">
              {metricValue(metric?.current_value, metric?.unit)}
            </div>
            <div className={`mt-2 flex items-center gap-1 text-xs font-medium ${trendColor(key, change)}`}>
              <span>{change == null ? '•' : change > 0 ? '↑' : '↓'}</span>
              {change == null ? 'No prior period' : `${Math.abs(change).toFixed(1)}% vs prior month`}
            </div>
          </article>
        );
      })}
    </div>
  );
}
