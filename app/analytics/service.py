from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb

from app.models.analytics import (
    CostAnalysis, DataQualityWarning, ExperienceAnalysis, MetricComparison,
    MonthlyOverview, SafetyAnalysis, ShiftReadiness, VendorAnalysis, VendorResult,
)

DB_DEFAULT = Path("data/processed/mobility.duckdb")
RATING_DIMS = ("route", "driver", "cab", "safety", "marshal")


def _rows(cursor: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    columns = [item[0] for item in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _one(connection: duckdb.DuckDBPyConnection, sql: str, params: list[Any]) -> dict[str, Any] | None:
    result = _rows(connection.execute(sql, params))
    return result[0] if result else None


def _round(value: Any, digits: int = 4) -> Any:
    return round(float(value), digits) if isinstance(value, (float, int)) and value is not None else value


def safe_rate(numerator: float | int | None, denominator: float | int | None) -> float | None:
    if numerator is None or denominator in (None, 0): return None
    return float(numerator) / float(denominator)


def compare_values(current: float | int | None, baseline: float | int | None) -> tuple[float | None, float | None]:
    if current is None or baseline is None: return None, None
    absolute = float(current) - float(baseline)
    relative = None if baseline == 0 else absolute / abs(float(baseline)) * 100
    return _round(absolute), _round(relative, 2)


class AnalyticsService:
    def __init__(self, database_path: Path = DB_DEFAULT): self.database_path = database_path

    def _connect(self) -> duckdb.DuckDBPyConnection:
        if not self.database_path.exists(): raise FileNotFoundError(f"DuckDB not found: {self.database_path}")
        return duckdb.connect(str(self.database_path), read_only=True)

    def _months(self, connection: duckdb.DuckDBPyConnection) -> list[str]:
        return [r[0] for r in connection.execute("SELECT month FROM monthly_metrics ORDER BY month").fetchall()]

    def _require_month(self, connection: duckdb.DuckDBPyConnection, month: str) -> None:
        if month not in self._months(connection): raise ValueError(f"Unknown month: {month}")

    def get_monthly_overview(self, month: str) -> MonthlyOverview:
        mapping = {
            "total_trips": ("trips", "count", "trips"), "delayed_trips": ("delayed_trips", "count", "trips"),
            "delay_rate": ("delay_rate", "rate", "trips"), "average_delay_minutes": ("avg_delay_minutes", "minutes", "delayed_trips"),
            "rider_legs": ("rider_legs", "count", "rider_legs"), "late_pickup_rate_5m": ("late_pickup_rate_5m", "rate", "pickup_sample"),
            "no_show_rate": ("no_show_rate", "rate", "rider_legs"), "safety_alert_count": ("alerts", "count", "trips"),
            "alerts_per_1000_trips": ("alerts_per_1000_trips", "per_1000_trips", "trips"),
            "total_billing_amount": ("total_billing", "currency_units", "bill_rows"), "average_billing_amount": ("avg_billing", "currency_units", "bill_rows"),
            "ev_share": ("ev_share", "rate", "trips"), "nonzero_safety_rating": ("nz_safety_rating", "rating_0_5", "feedback_rows"),
        }
        with self._connect() as c:
            self._require_month(c, month); months=self._months(c); idx=months.index(month)
            previous=months[idx-1] if idx else None; baseline=months[0] if months[0] != month else None
            cur=_one(c,"SELECT * FROM monthly_metrics WHERE month=?",[month]) or {}
            prev=_one(c,"SELECT * FROM monthly_metrics WHERE month=?",[previous]) if previous else None
            base=_one(c,"SELECT * FROM monthly_metrics WHERE month=?",[baseline]) if baseline else None
        metrics={}
        for name,(column,unit,sample_col) in mapping.items():
            cv=cur.get(column); pv=prev.get(column) if prev else None; bv=base.get(column) if base else None
            absolute,relative=compare_values(cv,pv)
            metrics[name]=MetricComparison(metric=name,current_value=_round(cv),previous_value=_round(pv),baseline_value=_round(bv),absolute_change=absolute,relative_change_pct=relative,unit=unit,sample_size=cur.get(sample_col))
        return MonthlyOverview(month=month,previous_month=previous,baseline_month=baseline,metrics=metrics,
            data_quality_warnings=[DataQualityWarning(code="rating_zero_semantics",message="Zero ratings excluded from non-zero rating metric; may mean not-rated/not-applicable.")])

    def compare_vendor_performance(self,current_month:str,baseline_month:str)->VendorAnalysis:
        with self._connect() as c:
            self._require_month(c,current_month); self._require_month(c,baseline_month)
            current=_rows(c.execute("SELECT *,rank() OVER(ORDER BY delay_rate,alerts_per_1000_trips) peer_rank FROM vendor_monthly_metrics WHERE month=?",[current_month]))
            bases={r['vendor']:r for r in _rows(c.execute("SELECT * FROM vendor_monthly_metrics WHERE month=?",[baseline_month]))}
        vendors=[]
        fields={"trip_volume":("trips","count"),"delay_rate":("delay_rate","rate"),"average_delay_minutes":("avg_delay_minutes","minutes"),"alerts_per_1000_trips":("alerts_per_1000_trips","per_1000_trips"),"no_show_rate":("no_show_rate","rate"),"average_billing":("avg_billing","currency_units"),"cost_per_km":("cost_per_km","currency_per_km"),"nonzero_rating":("nonzero_rating","rating_0_5")}
        for row in current:
            base=bases.get(row['vendor'],{}); metrics={}; score=0.0
            for name,(col,unit) in fields.items():
                cv=row.get(col); bv=base.get(col); change,rel=compare_values(cv,bv)
                metrics[name]=MetricComparison(metric=name,current_value=_round(cv),baseline_value=_round(bv),absolute_change=change,relative_change_pct=rel,unit=unit,sample_size=row.get('trips'))
            if metrics['delay_rate'].absolute_change: score += metrics['delay_rate'].absolute_change*100
            if metrics['alerts_per_1000_trips'].relative_change_pct: score += max(0,metrics['alerts_per_1000_trips'].relative_change_pct)/100
            vendors.append(VendorResult(vendor=row['vendor'],month=current_month,rank=row['peer_rank'],metrics=metrics,deterioration_score=_round(score)))
        vendors.sort(key=lambda x:x.deterioration_score,reverse=True)
        return VendorAnalysis(current_month=current_month,baseline_month=baseline_month,vendors=vendors)

    def analyze_vendor(self,vendor:str,month:str,baseline_month:str|None=None)->VendorResult:
        analysis=self.compare_vendor_performance(month,baseline_month or self._previous_month(month))
        for result in analysis.vendors:
            if result.vendor==vendor:return result
        raise ValueError(f"Unknown vendor for {month}: {vendor}")

    def _previous_month(self,month:str)->str:
        with self._connect() as c:
            self._require_month(c,month); months=self._months(c); idx=months.index(month)
            if idx==0: raise ValueError(f"No baseline month before {month}")
            return months[idx-1]

    def get_shift_readiness(self,month:str)->ShiftReadiness:
        with self._connect() as c:
            self._require_month(c,month)
            rows=_rows(c.execute("""SELECT *, late_5m::DOUBLE/nullif(pickup_sample,0) late_5m_rate,
            late_10m::DOUBLE/nullif(pickup_sample,0) late_10m_rate,no_shows::DOUBLE/nullif(rider_legs,0) no_show_rate,
            round(100*(0.25*late_5m_rate+0.45*late_10m_rate+0.30*no_show_rate),2) risk_score
            FROM shift_monthly_metrics WHERE month=? ORDER BY risk_score DESC NULLS LAST""",[month]))
        return ShiftReadiness(month=month,shifts=[{k:_round(v) for k,v in r.items()} for r in rows])

    def analyze_safety_alerts(self,month:str,vendor:str|None=None,office:str|None=None)->SafetyAnalysis:
        filters=["a.month=?"];params:[Any]=[month]
        if vendor:filters.append("d.vendor=?");params.append(vendor)
        if office:filters.append("d.office=?");params.append(office)
        where=" AND ".join(filters)
        with self._connect() as c:
            self._require_month(c,month)
            alerts=_one(c,f"SELECT count(*) n,avg(epoch(a.acknowledge_time-a.start_time)/60.0) FILTER(WHERE a.acknowledge_time>=a.start_time) avg_ack,count(*) FILTER(WHERE a.acknowledge_time IS NULL) unacked FROM alerts a LEFT JOIN trip_dimension d USING(month,trip_id) WHERE {where}",params) or {}
            trip_filters=["month=?"];trip_params:[Any]=[month]
            if vendor:trip_filters.append("vendor_id=?");trip_params.append(vendor)
            if office:trip_filters.append("office=?");trip_params.append(office)
            trips=c.execute(f"SELECT count(*) FROM rides WHERE {' AND '.join(trip_filters)}",trip_params).fetchone()[0]
            def dist(column:str):return _rows(c.execute(f"SELECT coalesce(cast(a.{column} as varchar),'UNKNOWN') AS category,count(*) AS count FROM alerts a LEFT JOIN trip_dimension d USING(month,trip_id) WHERE {where} GROUP BY 1 ORDER BY 2 DESC",params))
            severities=dist('severity'); event_types=dist('event_type')
            vendors=_rows(c.execute(f"SELECT coalesce(d.vendor,'UNMATCHED') vendor,count(*) count FROM alerts a LEFT JOIN trip_dimension d USING(month,trip_id) WHERE {where} GROUP BY 1 ORDER BY 2 DESC",params))
            offices=_rows(c.execute(f"SELECT coalesce(d.office,'UNMATCHED') office,count(*) count FROM alerts a LEFT JOIN trip_dimension d USING(month,trip_id) WHERE {where} GROUP BY 1 ORDER BY 2 DESC",params))
            vehicles=_rows(c.execute(f"SELECT d.vehicle,count(*) count FROM alerts a JOIN trip_dimension d USING(month,trip_id) WHERE {where} AND d.vehicle IS NOT NULL GROUP BY 1 HAVING count(*)>1 ORDER BY 2 DESC LIMIT 20",params))
        count=int(alerts.get('n',0)); warnings=[]
        if any(r['category'] in ('False','UNKNOWN') for r in severities):warnings.append(DataQualityWarning(code='invalid_or_missing_severity',message='Severity includes invalid or missing values.'))
        return SafetyAnalysis(month=month,filters={'vendor':vendor,'office':office},alert_count=count,trip_count=trips,alerts_per_1000_trips=_round(safe_rate(count*1000,trips)),severity_distribution=severities,alert_type_distribution=event_types,vendor_concentration=vendors,office_concentration=offices,acknowledgement_minutes={'average':_round(alerts.get('avg_ack')),'unacknowledged':alerts.get('unacked')},repeated_vehicle_patterns=vehicles,data_quality_warnings=warnings)

    def analyze_delay_causes(self,month:str,vendor:str|None=None,office:str|None=None,shift:str|None=None)->dict[str,Any]:
        filters=["month=?"];params:[Any]=[month]
        for column,value in [('vendor',vendor),('office',office),('shift_type',shift)]:
            if value:filters.append(f"{column}=?");params.append(value)
        with self._connect() as c:
            self._require_month(c,month)
            rows=_rows(c.execute(f"SELECT delay_reason,sum(trip_count) trip_count,sum(total_delay_minutes) total_delay_minutes,avg(avg_delay_minutes) avg_delay_minutes FROM delay_reason_metrics WHERE {' AND '.join(filters)} GROUP BY 1 ORDER BY trip_count DESC",params))
            ride_filters=["month=?","delay_minutes>0"];ride_params:[Any]=[month]
            for column,value in [('vendor_id',vendor),('office',office),('shift_type',shift)]:
                if value:ride_filters.append(f"{column}=?");ride_params.append(value)
            trips=_rows(c.execute(f"SELECT trip_id,office,shift_type,vendor_id vendor,delay_reason,delay_minutes FROM rides WHERE {' AND '.join(ride_filters)} ORDER BY delay_minutes DESC LIMIT 50",ride_params))
        return {'month':month,'filters':{'vendor':vendor,'office':office,'shift':shift},'reasons':[{k:_round(v) for k,v in r.items()} for r in rows],'trip_evidence':[{k:_round(v) for k,v in r.items()} for r in trips]}

    def analyze_cost(self,month:str,vendor:str|None=None)->CostAnalysis:
        with self._connect() as c:
            self._require_month(c,month); clause="month=?"+(" AND vendor=?" if vendor else "");params=[month]+([vendor] if vendor else [])
            row=_one(c,f"SELECT sum(billed_rows) billed_rows,sum(total_billing) total_billing,sum(total_billing)/nullif(sum(billed_rows),0) avg_billing,sum(valid_distance_rows) valid_rows,sum(excluded_distance_rows) excluded_rows,sum(valid_distance_km) valid_km,sum(valid_distance_cost)/nullif(sum(valid_distance_km),0) cost_per_km FROM cost_monthly_metrics WHERE {clause}",params)
            if not row or row['billed_rows'] is None:raise ValueError(f"No billing data for {vendor or 'all vendors'} in {month}")
        coverage=100*row['valid_rows']/row['billed_rows'];warnings=[]
        if row['excluded_rows']:warnings.append(DataQualityWarning(code='invalid_cost_or_distance_excluded',message='Zero/negative/missing distance or negative/missing cost rows excluded from cost/km.',affected_rows=row['excluded_rows']))
        return CostAnalysis(month=month,vendor=vendor,billed_rows=row['billed_rows'],total_billing_amount=_round(row['total_billing'],2),average_billing_amount=_round(row['avg_billing'],2),valid_distance_rows=row['valid_rows'],excluded_distance_rows=row['excluded_rows'],distance_metric_coverage_pct=_round(coverage,2),total_valid_distance_km=_round(row['valid_km'],2),cost_per_km=_round(row['cost_per_km'],2),data_quality_warnings=warnings)

    def get_experience_metrics(self,month:str,vendor:str|None=None)->ExperienceAnalysis:
        join="JOIN trip_dimension d USING(month,trip_id)" if vendor else "";where="f.month=?"+(" AND d.vendor=?" if vendor else "");params=[month]+([vendor] if vendor else [])
        expressions=[]
        for dim in RATING_DIMS:expressions += [f"avg({dim}_rating) raw_{dim}",f"avg({dim}_rating) FILTER(WHERE {dim}_rating>0) nz_{dim}",f"count(*) FILTER(WHERE {dim}_rating=0) zero_{dim}"]
        with self._connect() as c:
            self._require_month(c,month);row=_one(c,f"SELECT count(*) feedback_rows,{','.join(expressions)} FROM feedback f {join} WHERE {where}",params) or {}
        dims={d:{'raw_average':_round(row.get('raw_'+d)),'nonzero_average':_round(row.get('nz_'+d)),'zero_count':row.get('zero_'+d)} for d in RATING_DIMS}
        return ExperienceAnalysis(month=month,vendor=vendor,feedback_rows=row.get('feedback_rows',0),dimensions=dims,data_quality_warnings=[DataQualityWarning(code='rating_zero_semantics',message='Zero may mean not-rated/not-applicable; non-zero averages are primary.')])

    def get_data_quality_report(self)->dict[str,Any]:
        path=self.database_path.parent/'data_quality_summary.json';base=json.loads(path.read_text()) if path.exists() else {}
        with self._connect() as c:
            missing={t:int(c.execute(f"SELECT count(*) FROM {t} WHERE trip_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM rides r WHERE r.month={t}.month AND r.trip_id={t}.trip_id)").fetchone()[0]) for t in ['alerts','bills','feedback','employees']}
            ambiguous=int(c.execute("SELECT count(*) FROM trip_dimension WHERE vendor_mapping_count>1 OR office_mapping_count>1").fetchone()[0])
            high_null=_rows(c.execute("SELECT 'alerts.acknowledge_time' field,count(*) FILTER(WHERE acknowledge_time IS NULL) null_rows,count(*) total_rows FROM alerts UNION ALL SELECT 'alerts.severity',count(*) FILTER(WHERE severity IS NULL),count(*) FROM alerts UNION ALL SELECT 'bills.slab_name',count(*) FILTER(WHERE slab_name IS NULL),count(*) FROM bills"))
        return {'preprocessing':base,'missing_ride_joins':missing,'ambiguous_trip_dimensions':ambiguous,'high_null_fields':high_null,'warnings':['Zero ratings have ambiguous semantics.','Severity contains False and null values.','Zero-distance bill rows excluded from normalized cost metrics.']}


def get_monthly_overview(month:str):return AnalyticsService().get_monthly_overview(month)
def compare_vendor_performance(current_month:str,baseline_month:str):return AnalyticsService().compare_vendor_performance(current_month,baseline_month)
def analyze_vendor(vendor:str,month:str,baseline_month:str|None=None):return AnalyticsService().analyze_vendor(vendor,month,baseline_month)
def get_shift_readiness(month:str):return AnalyticsService().get_shift_readiness(month)
def analyze_safety_alerts(month:str,vendor:str|None=None,office:str|None=None):return AnalyticsService().analyze_safety_alerts(month,vendor,office)
def analyze_delay_causes(month:str,vendor:str|None=None,office:str|None=None,shift:str|None=None):return AnalyticsService().analyze_delay_causes(month,vendor,office,shift)
def analyze_cost(month:str,vendor:str|None=None):return AnalyticsService().analyze_cost(month,vendor)
def get_experience_metrics(month:str,vendor:str|None=None):return AnalyticsService().get_experience_metrics(month,vendor)
def get_data_quality_report():return AnalyticsService().get_data_quality_report()
