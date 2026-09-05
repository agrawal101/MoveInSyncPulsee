import { ApiError } from '../../api/client';

export function Loading({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-3" aria-label="Pulse is investigating operational evidence">
      <p className="text-sm font-medium text-slate-500">
        Pulse is investigating operational evidence…
      </p>
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="skeleton h-20 rounded-xl" />
      ))}
    </div>
  );
}

export function ErrorState({ error, retry }: { error: Error; retry: () => void }) {
  const unavailable = error instanceof ApiError && error.status === 503;
  return (
    <div className="card border-amber-200 p-6">
      <div className="mb-1 font-semibold text-navy">
        {unavailable ? 'AI reasoning is unavailable' : 'Unable to load this view'}
      </div>
      <p className="mb-4 text-sm text-slate-600">
        {unavailable
          ? 'Deterministic mobility analytics are still operational. Configure the LLM to enable this feature.'
          : error.message}
      </p>
      <button className="btn-secondary" onClick={retry}>Retry</button>
    </div>
  );
}

export function Empty({ message }: { message: string }) {
  return <div className="card p-8 text-center text-slate-500">{message}</div>;
}
