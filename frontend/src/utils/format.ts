export const pct=(value:number|null|undefined,digits=1)=>value==null?'—':`${(value*100).toFixed(digits)}%`;
export const num=(value:number|null|undefined,digits=0)=>value==null?'—':new Intl.NumberFormat('en-US',{maximumFractionDigits:digits}).format(value);
export const compact=(value:number|null|undefined)=>value==null?'—':new Intl.NumberFormat('en-US',{notation:'compact',maximumFractionDigits:2}).format(value);
export const metricValue=(value:number|null|undefined,unit:string)=>unit==='rate'?pct(value):unit==='per_1000_trips'?num(value,2):unit==='currency_units'?compact(value):unit==='rating_0_5'?num(value,2):num(value,2);
export const monthLabel=(month:string)=>new Date(`${month}-01T00:00:00`).toLocaleDateString('en-US',{month:'long',year:'numeric'});
export const baselineFor=(month:string)=>month==='2026-05'?'2026-05':month==='2026-06'?'2026-05':'2026-06';
