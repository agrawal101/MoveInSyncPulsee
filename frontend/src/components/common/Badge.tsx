import type{Severity}from'../../api/types';
const styles:Record<Severity,string>={high:'bg-red-50 text-red-700 ring-red-200',medium:'bg-amber-50 text-amber-700 ring-amber-200',positive:'bg-emerald-50 text-emerald-700 ring-emerald-200',low:'bg-slate-100 text-slate-600 ring-slate-200',informational:'bg-blue-50 text-blue-700 ring-blue-200'};
export function SeverityBadge({value}:{value:Severity}){return <span className={`badge ring-1 ring-inset ${styles[value]}`}>{value}</span>}
