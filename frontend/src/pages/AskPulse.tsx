import { useState } from 'react';

import { api } from '../api/client';
import type { AgentResponse } from '../api/types';
import { SeverityBadge } from '../components/common/Badge';
import { ErrorState, Loading } from '../components/common/States';
import { baselineFor } from '../utils/format';

const prompts = [
  'Which vendor should I investigate first?',
  'What changed this month?',
  'Why is Aarav Petrov Travel high risk?',
  'Which shift has the highest pickup risk?',
  'What caused the most delays?',
  'Are cost metrics reliable?',
  'What improved since last month?',
];

export function AskPulse({
  month,
  initialQuestion,
  onConsumed,
}: {
  month: string;
  initialQuestion: string;
  onConsumed: () => void;
}) {
  const [question, setQuestion] = useState(initialQuestion);
  const [data, setData] = useState<AgentResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const submit = async () => {
    if (!question.trim()) return;
    setLoading(true);
    setError(null);
    onConsumed();
    try {
      setData(await api.queryAgent(question, month, baselineFor(month)));
    } catch (caught) {
      setError(caught as Error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-5xl">
      <header>
        <div className="eyebrow text-blue-600">Enterprise analyst</div>
        <h1 className="mt-1 text-2xl font-semibold">Ask Pulse</h1>
        <p className="mt-1 text-slate-500">
          Ask an operational question. Pulse selects approved analytics and returns
          evidence-backed guidance.
        </p>
      </header>
      <section className="card mt-6 p-5">
        <label htmlFor="pulse-question" className="text-sm font-semibold">
          What do you need to understand?
        </label>
        <div className="mt-3 flex gap-3">
          <textarea
            id="pulse-question"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                void submit();
              }
            }}
            rows={2}
            className="min-h-[64px] flex-1 resize-none rounded-lg border border-slate-300 px-4 py-3 text-base"
            placeholder="Ask about vendors, shifts, safety, cost, or monthly changes…"
          />
          <button
            className="btn-primary w-28"
            disabled={loading || !question.trim()}
            onClick={() => void submit()}
          >
            {loading ? 'Analyzing…' : 'Analyze'}
          </button>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          {prompts.map((prompt) => (
            <button
              key={prompt}
              onClick={() => setQuestion(prompt)}
              className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs text-slate-600 hover:border-blue-300 hover:text-blue-700"
            >
              {prompt}
            </button>
          ))}
        </div>
      </section>
      <div className="mt-6">
        {loading && <Loading rows={4} />}
        {error && <ErrorState error={error} retry={() => void submit()} />}
        {data && <Response data={data} />}
      </div>
    </div>
  );
}

function Response({ data }: { data: AgentResponse }) {
  return (
    <div className="space-y-4">
      {data.synthesis_mode === 'deterministic_fallback' && (
        <div role="status" className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          AI synthesis unavailable — showing analytics-backed summary.
        </div>
      )}
      <section className="card p-6">
        <div className="flex justify-between">
          <div className="eyebrow">Pulse answer</div>
          <div className="flex gap-2">
            <SeverityBadge value={data.severity} />
            <span className="badge bg-slate-100 text-slate-600">
              {data.confidence} confidence
            </span>
          </div>
        </div>
        <h2 className="mt-3 text-lg font-semibold">{data.summary}</h2>
        <p className="mt-2 leading-7 text-slate-600">{data.answer}</p>
      </section>
      <details open className="card p-5">
        <summary className="cursor-pointer font-semibold">Findings</summary>
        <div className="mt-3 divide-y divide-slate-100">
          {data.findings.map((finding, index) => (
            <div key={index} className="py-3">
              <b>{finding.title}</b>
              <p className="mt-1 text-sm text-slate-600">{finding.description}</p>
              <FindingValues finding={finding} />
            </div>
          ))}
        </div>
      </details>
      <details className="card p-5">
        <summary className="cursor-pointer font-semibold">Recommended actions</summary>
        <div className="mt-3 space-y-3">
          {data.recommended_actions.map((action, index) => (
            <div key={index}>
              <b>{action.title}</b>
              <p className="text-sm text-slate-600">{action.description}</p>
            </div>
          ))}
        </div>
      </details>
      {data.data_quality_warnings.length > 0 && (
        <details className="card border-amber-200 p-5">
          <summary className="cursor-pointer font-semibold text-amber-800">
            Data-quality warnings
          </summary>
          <ul className="mt-3 space-y-1 text-sm text-amber-800">
            {data.data_quality_warnings.map((warning) => (
              <li key={warning}>⚠ {warning}</li>
            ))}
          </ul>
        </details>
      )}
      <details className="card p-4">
        <summary className="cursor-pointer text-sm font-semibold">Analysis details</summary>
        <div className="mt-3 text-xs text-slate-500">
          <p>Analyzed with Pulse AI</p>
          {data.execution?.provider && <p className="mt-1">Provider: {data.execution.provider}</p>}
          <p className="mt-1">Analysis time: {data.execution?.duration_ms} ms</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {data.execution?.tools_called.map((tool) => (
              <span
                className="rounded-md bg-blue-50 px-2 py-1 font-medium text-blue-700"
                key={tool}
              >
                {tool.replace(/_tool$/, '').replaceAll('_', ' ')}
              </span>
            ))}
          </div>
        </div>
      </details>
    </div>
  );
}

function FindingValues({ finding }: { finding: AgentResponse['findings'][number] }) {
  const candidates: Array<[string, number | null]> = [
    ['current', finding.current_value],
    ['baseline', finding.baseline_value],
    ['change', finding.change],
    ['sample', finding.sample_size],
  ];
  const values = candidates.filter((item): item is [string, number] => item[1] !== null);
  if (!finding.metric || values.length === 0) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-2 font-mono text-xs text-blue-700">
      <span className="rounded bg-blue-50 px-2 py-1">
        {finding.metric.replaceAll('_', ' ')}
      </span>
      {values.map(([label, value]) => (
        <span className="rounded bg-slate-50 px-2 py-1" key={label}>
          {label}: {String(value)}
        </span>
      ))}
    </div>
  );
}
