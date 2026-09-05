import type { ReactNode } from 'react';
import type { AgentResponse, CrossDomainSignal, Investigable } from '../../api/types';
import { isCrossDomain } from '../../api/types';
import { SeverityBadge } from '../common/Badge';
import { ErrorState, Loading } from '../common/States';
import { SignalChip, signalArrow } from '../anomalies/CrossSignalCard';

const toolLabel = (name: string) =>
  name
    .replace(/_tool$/, '')
    .replaceAll('_', ' ')
    .replace(/^./, (c) => c.toUpperCase());

const fmt = (v: number | null) => (v == null ? '—' : Number.isInteger(v) ? String(v) : v.toFixed(3));

function CategoryTitle({ anomaly }: { anomaly: Investigable }) {
  const title = isCrossDomain(anomaly) ? anomaly.title : anomaly.entity_name;
  return (
    <>
      <div className="eyebrow text-blue-600">Pulse Investigation</div>
      <h2 className="mt-1 text-xl font-semibold">{title}</h2>
      <div className="text-sm text-slate-500">{anomaly.entity_name}</div>
      <div className="mt-2 flex items-center gap-2">
        <SeverityBadge value={anomaly.severity} />
        {isCrossDomain(anomaly) && (
          <span className="text-xs font-medium text-slate-500">
            {anomaly.category.replaceAll('_', ' ')} · risk{' '}
            {anomaly.cross_signal_risk_score.toFixed(1)}
          </span>
        )}
      </div>
    </>
  );
}

function SignalRow({ s }: { s: CrossDomainSignal }) {
  return (
    <div className="flex items-center justify-between border-b border-slate-100 py-2 last:border-0">
      <SignalChip signal={s} />
      <div className="flex items-center gap-4 font-mono text-xs text-slate-600">
        <span title="current">{fmt(s.current_value)}</span>
        <span className="text-slate-400" title="baseline">
          base {fmt(s.baseline_value)}
        </span>
        <span className="text-slate-400" title="peer median">
          peer {fmt(s.peer_median)}
        </span>
        <span className="w-4 text-center">{signalArrow(s)}</span>
      </div>
    </div>
  );
}

function CrossSections({ anomaly, data }: { anomaly: Investigable; data: AgentResponse }) {
  if (!isCrossDomain(anomaly)) return null;
  const historical = anomaly.signals.filter((s) => s.baseline_value != null);
  const peer = anomaly.signals.filter((s) => s.peer_median != null);
  return (
    <>
      <Panel title="Why this was flagged">
        <p className="leading-6 text-slate-700">{anomaly.why_flagged}</p>
      </Panel>
      <Panel title="Signals correlated">
        <div className="mb-3 flex flex-wrap gap-1.5">
          {anomaly.signals.map((s, i) => (
            <SignalChip key={i} signal={s} />
          ))}
        </div>
        {anomaly.signals.map((s, i) => (
          <SignalRow key={i} s={s} />
        ))}
      </Panel>
      {historical.length > 0 && (
        <Panel title="Historical comparison">
          <div className="text-sm text-slate-600">
            Compared against baseline month{' '}
            <b>{anomaly.baseline_month ?? '—'}</b>. Values shown per signal above (current vs
            base).
          </div>
        </Panel>
      )}
      {peer.length > 0 && (
        <Panel title="Peer comparison">
          <ul className="space-y-1 text-sm text-slate-600">
            {peer.map((s, i) => (
              <li key={i}>
                {s.metric.replaceAll('_', ' ')}: <b>{fmt(s.current_value)}</b> vs peer median{' '}
                <b>{fmt(s.peer_median)}</b>
              </li>
            ))}
          </ul>
        </Panel>
      )}
      <Panel title="Business interpretation">
        <p className="leading-6 text-slate-700">{data.answer}</p>
      </Panel>
      <Panel title="Cross-signal risk score">
        <div className="mb-2 text-2xl font-semibold text-navy">
          {anomaly.cross_signal_risk_score.toFixed(1)}
          <span className="ml-2 text-sm font-normal text-slate-500">/ 100 · explainable</span>
        </div>
        {anomaly.risk_components.map((c) => (
          <div key={c.name} className="flex items-center justify-between py-1 text-sm">
            <span className="text-slate-600">{c.name.replaceAll('_', ' ')}</span>
            <span className="font-mono text-slate-500">
              +{c.value.toFixed(1)} <span className="text-slate-400">· {c.detail}</span>
            </span>
          </div>
        ))}
      </Panel>
      <Panel title="Recommended investigation">
        <ol className="space-y-2">
          {anomaly.recommended_investigation.map((step, i) => (
            <li key={i} className="flex gap-3 text-sm">
              <span className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full bg-blue-50 text-xs font-bold text-blue-700">
                {i + 1}
              </span>
              <span className="text-slate-600">{step}</span>
            </li>
          ))}
        </ol>
      </Panel>
    </>
  );
}

export function InvestigationDrawer({
  anomaly,
  data,
  error,
  loading,
  onClose,
  onRetry,
}: {
  anomaly: Investigable | null;
  data: AgentResponse | null;
  error: Error | null;
  loading: boolean;
  onClose: () => void;
  onRetry: () => void;
}) {
  if (!anomaly) return null;
  const cross = isCrossDomain(anomaly);
  return (
    <div className="fixed inset-0 z-50 bg-navy/25" role="dialog" aria-modal="true" aria-label="Pulse Investigation">
      <aside className="absolute inset-y-0 right-0 w-[720px] overflow-y-auto bg-[#f7f9fb] shadow-2xl">
        <header className="sticky top-0 z-10 flex items-start justify-between border-b border-slate-200 bg-white px-7 py-5">
          <div>
            <CategoryTitle anomaly={anomaly} />
          </div>
          <button
            onClick={onClose}
            className="rounded-lg px-3 py-2 text-xl text-slate-500 hover:bg-slate-100"
            aria-label="Close investigation"
          >
            ×
          </button>
        </header>
        <div className="space-y-5 p-7">
          {loading && <Loading rows={5} />}
          {error && <ErrorState error={error} retry={onRetry} />}
          {data && (
            <>
              {cross && <CrossSections anomaly={anomaly} data={data} />}
              {!cross && (
                <>
                  <Panel title="Finding">
                    <p className="text-base font-semibold">{data.summary}</p>
                    <p className="mt-2 leading-6 text-slate-600">{data.answer}</p>
                  </Panel>
                  <Panel title="Supporting evidence">
                    {data.findings.map((f, i) => (
                      <div key={i} className="border-b border-slate-100 py-3 last:border-0">
                        <div className="font-semibold">{f.title}</div>
                        <div className="mt-1 text-sm text-slate-600">{f.description}</div>
                        {f.current_value != null && (
                          <div className="mt-2 font-mono text-xs text-blue-700">
                            {f.current_value}
                            {f.baseline_value != null && ' · baseline ' + f.baseline_value}
                          </div>
                        )}
                      </div>
                    ))}
                  </Panel>
                  <Panel title="Recommended actions">
                    {data.recommended_actions.map((a, i) => (
                      <div key={i} className="flex gap-3 py-2">
                        <span className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full bg-blue-50 text-xs font-bold text-blue-700">
                          {i + 1}
                        </span>
                        <div>
                          <div className="font-semibold">{a.title}</div>
                          <p className="mt-1 text-sm text-slate-600">{a.description}</p>
                        </div>
                      </div>
                    ))}
                  </Panel>
                </>
              )}
              <div className="flex items-center gap-3 text-xs">
                <span className="text-slate-500">
                  Confidence: <b className="capitalize text-navy">{data.confidence}</b>
                </span>
                {data.synthesis_mode === 'deterministic_fallback' && (
                  <span className="rounded bg-amber-50 px-2 py-0.5 font-medium text-amber-700">
                    analytics-backed (AI synthesis unavailable)
                  </span>
                )}
              </div>
              {data.data_quality_warnings.length > 0 && (
                <Panel title="Data-quality caveats">
                  <ul className="space-y-2 text-sm text-amber-800">
                    {data.data_quality_warnings.map((w) => (
                      <li key={w}>⚠ {w}</li>
                    ))}
                  </ul>
                </Panel>
              )}
              <Panel title="Tool activity">
                <div className="space-y-2">
                  {data.execution?.tools_called.map((name) => (
                    <div
                      key={name}
                      className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2 text-sm"
                    >
                      <span>
                        <b className="mr-2 text-emerald-600">✓</b>
                        {toolLabel(name)}
                      </span>
                      <span className="text-xs text-slate-400">
                        {data.execution?.tool_durations_ms[name]} ms
                      </span>
                    </div>
                  ))}
                  <div className="flex items-center gap-2 px-3 py-2 text-sm">
                    <b className="text-emerald-600">✓</b> Recommendation generated
                  </div>
                </div>
              </Panel>
              <div className="text-right text-xs text-slate-500">
                Total analysis: {data.execution?.duration_ms} ms
              </div>
            </>
          )}
        </div>
      </aside>
    </div>
  );
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="card p-5">
      <div className="eyebrow mb-3">{title}</div>
      {children}
    </section>
  );
}
