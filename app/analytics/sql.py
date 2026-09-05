AGGREGATE_SQL = r"""
CREATE OR REPLACE TABLE trip_dimension AS
SELECT month, trip_id, min(vendor_id) AS vendor, min(office) AS office,
       min(actual_cab_registration) AS vehicle,
       count(DISTINCT vendor_id) AS vendor_mapping_count,
       count(DISTINCT office) AS office_mapping_count
FROM rides WHERE trip_id IS NOT NULL GROUP BY month, trip_id;

CREATE OR REPLACE TABLE monthly_metrics AS
WITH months AS (SELECT DISTINCT month FROM rides),
r AS (SELECT month, count(*) trips, count(*) FILTER (WHERE delay_minutes > 0) delayed_trips,
 avg(delay_minutes) FILTER (WHERE delay_minutes > 0) avg_delay_minutes,
 count(*) FILTER (WHERE actual_cab_fuel_type='Electric') ev_trips FROM rides GROUP BY month),
e AS (SELECT month, count(*) rider_legs, count(*) FILTER (WHERE is_no_show) no_shows,
 count(*) FILTER (WHERE planned_pickup_epoch IS NOT NULL AND actual_pickup_epoch IS NOT NULL) pickup_sample,
 count(*) FILTER (WHERE actual_pickup_epoch-planned_pickup_epoch > 300) late_pickups_5m
 FROM employees GROUP BY month),
a AS (SELECT month,count(*) alerts FROM alerts GROUP BY month),
b AS (SELECT month,count(*) bill_rows,sum(trip_cost) total_billing,avg(trip_cost) avg_billing FROM bills GROUP BY month),
f AS (SELECT month,count(*) feedback_rows,
 avg(route_rating) raw_route_rating,avg(route_rating) FILTER(WHERE route_rating>0) nz_route_rating,
 avg(driver_rating) raw_driver_rating,avg(driver_rating) FILTER(WHERE driver_rating>0) nz_driver_rating,
 avg(cab_rating) raw_cab_rating,avg(cab_rating) FILTER(WHERE cab_rating>0) nz_cab_rating,
 avg(safety_rating) raw_safety_rating,avg(safety_rating) FILTER(WHERE safety_rating>0) nz_safety_rating,
 avg(marshal_rating) raw_marshal_rating,avg(marshal_rating) FILTER(WHERE marshal_rating>0) nz_marshal_rating
 FROM feedback GROUP BY month)
SELECT m.month,r.trips,r.delayed_trips,r.delayed_trips::DOUBLE/nullif(r.trips,0) delay_rate,
 r.avg_delay_minutes,r.ev_trips,r.ev_trips::DOUBLE/nullif(r.trips,0) ev_share,
 e.rider_legs,e.no_shows,e.no_shows::DOUBLE/nullif(e.rider_legs,0) no_show_rate,
 e.pickup_sample,e.late_pickups_5m,e.late_pickups_5m::DOUBLE/nullif(e.pickup_sample,0) late_pickup_rate_5m,
 coalesce(a.alerts,0) alerts,coalesce(a.alerts,0)*1000.0/nullif(r.trips,0) alerts_per_1000_trips,
 b.bill_rows,b.total_billing,b.avg_billing,f.* EXCLUDE(month)
FROM months m JOIN r USING(month) LEFT JOIN e USING(month) LEFT JOIN a USING(month)
LEFT JOIN b USING(month) LEFT JOIN f USING(month);

CREATE OR REPLACE TABLE vendor_monthly_metrics AS
WITH rv AS (
 SELECT month,vendor_id vendor,count(*) trips,count(*) FILTER(WHERE delay_minutes>0) delayed_trips,
 avg(delay_minutes) FILTER(WHERE delay_minutes>0) avg_delay_minutes
 FROM rides GROUP BY month,vendor_id),
av AS (SELECT a.month,d.vendor,count(*) alerts FROM alerts a JOIN trip_dimension d USING(month,trip_id) GROUP BY a.month,d.vendor),
ev AS (SELECT e.month,d.vendor,count(*) rider_legs,count(*) FILTER(WHERE e.is_no_show) no_shows
 FROM employees e JOIN trip_dimension d USING(month,trip_id) GROUP BY e.month,d.vendor),
bv AS (SELECT month,vendor,count(*) bill_rows,sum(trip_cost) total_billing,avg(trip_cost) avg_billing,
 count(*) FILTER(WHERE total_trip_km>0 AND trip_cost>=0) valid_distance_rows,
 sum(trip_cost) FILTER(WHERE total_trip_km>0 AND trip_cost>=0)/nullif(sum(total_trip_km) FILTER(WHERE total_trip_km>0 AND trip_cost>=0),0) cost_per_km
 FROM bills GROUP BY month,vendor),
fv AS (SELECT f.month,d.vendor,count(*) feedback_rows,
 avg((f.route_rating+f.driver_rating+f.cab_rating+f.safety_rating+f.marshal_rating)/5.0) raw_rating,
 avg((nullif(f.route_rating,0)+nullif(f.driver_rating,0)+nullif(f.cab_rating,0)+nullif(f.safety_rating,0)+nullif(f.marshal_rating,0)) /
 nullif((f.route_rating>0)::INT+(f.driver_rating>0)::INT+(f.cab_rating>0)::INT+(f.safety_rating>0)::INT+(f.marshal_rating>0)::INT,0)) nonzero_rating
 FROM feedback f JOIN trip_dimension d USING(month,trip_id) GROUP BY f.month,d.vendor)
SELECT rv.*,rv.delayed_trips::DOUBLE/nullif(rv.trips,0) delay_rate,
 coalesce(av.alerts,0) alerts,coalesce(av.alerts,0)*1000.0/nullif(rv.trips,0) alerts_per_1000_trips,
 ev.rider_legs,ev.no_shows,ev.no_shows::DOUBLE/nullif(ev.rider_legs,0) no_show_rate,
 bv.bill_rows,bv.total_billing,bv.avg_billing,bv.valid_distance_rows,bv.cost_per_km,
 fv.feedback_rows,fv.raw_rating,fv.nonzero_rating
FROM rv LEFT JOIN av USING(month,vendor) LEFT JOIN ev USING(month,vendor)
LEFT JOIN bv USING(month,vendor) LEFT JOIN fv USING(month,vendor);

CREATE OR REPLACE TABLE shift_monthly_metrics AS
SELECT e.month,e.shift_type,count(*) rider_legs,
 count(*) FILTER(WHERE e.planned_pickup_epoch IS NOT NULL AND e.actual_pickup_epoch IS NOT NULL) pickup_sample,
 avg((e.actual_pickup_epoch-e.planned_pickup_epoch)/60.0) FILTER(WHERE e.planned_pickup_epoch IS NOT NULL AND e.actual_pickup_epoch IS NOT NULL) avg_pickup_delay_minutes,
 count(*) FILTER(WHERE e.actual_pickup_epoch-e.planned_pickup_epoch>300) late_5m,
 count(*) FILTER(WHERE e.actual_pickup_epoch-e.planned_pickup_epoch>600) late_10m,
 count(*) FILTER(WHERE e.is_no_show) no_shows,
 count(DISTINCT e.office) offices,
 count(DISTINCT d.vendor) vendors
FROM employees e LEFT JOIN trip_dimension d USING(month,trip_id) GROUP BY e.month,e.shift_type;

CREATE OR REPLACE TABLE vendor_safety_metrics AS
SELECT a.month,d.vendor,count(*) alert_count,
 count(*) FILTER(WHERE a.severity='Sev-1') sev1_count,
 avg(epoch(a.acknowledge_time-a.start_time)/60.0) FILTER(WHERE a.acknowledge_time>=a.start_time) avg_ack_minutes
FROM alerts a JOIN trip_dimension d USING(month,trip_id) GROUP BY a.month,d.vendor;

CREATE OR REPLACE TABLE office_monthly_metrics AS
SELECT month,office,count(*) trips,count(*) FILTER(WHERE delay_minutes>0) delayed_trips,
 avg(delay_minutes) FILTER(WHERE delay_minutes>0) avg_delay_minutes
FROM rides GROUP BY month,office;

CREATE OR REPLACE TABLE delay_reason_metrics AS
SELECT month,office,shift_type,vendor_id vendor,delay_reason,count(*) trip_count,
 sum(delay_minutes) total_delay_minutes,avg(delay_minutes) avg_delay_minutes
FROM rides WHERE delay_minutes>0 GROUP BY month,office,shift_type,vendor_id,delay_reason;

CREATE OR REPLACE TABLE cost_monthly_metrics AS
SELECT month,vendor,count(*) billed_rows,sum(trip_cost) total_billing,avg(trip_cost) avg_billing,
 count(*) FILTER(WHERE total_trip_km>0 AND trip_cost>=0) valid_distance_rows,
 count(*) FILTER(WHERE total_trip_km IS NULL OR total_trip_km<=0 OR trip_cost IS NULL OR trip_cost<0) excluded_distance_rows,
 sum(total_trip_km) FILTER(WHERE total_trip_km>0 AND trip_cost>=0) valid_distance_km,
 sum(trip_cost) FILTER(WHERE total_trip_km>0 AND trip_cost>=0) valid_distance_cost,
 sum(trip_cost) FILTER(WHERE total_trip_km>0 AND trip_cost>=0)/nullif(sum(total_trip_km) FILTER(WHERE total_trip_km>0 AND trip_cost>=0),0) cost_per_km
FROM bills GROUP BY month,vendor;

CREATE OR REPLACE TABLE feedback_monthly_metrics AS
SELECT month,count(*) feedback_rows,
 avg(route_rating) raw_route,avg(route_rating) FILTER(WHERE route_rating>0) nonzero_route,
 avg(driver_rating) raw_driver,avg(driver_rating) FILTER(WHERE driver_rating>0) nonzero_driver,
 avg(cab_rating) raw_cab,avg(cab_rating) FILTER(WHERE cab_rating>0) nonzero_cab,
 avg(safety_rating) raw_safety,avg(safety_rating) FILTER(WHERE safety_rating>0) nonzero_safety,
 avg(marshal_rating) raw_marshal,avg(marshal_rating) FILTER(WHERE marshal_rating>0) nonzero_marshal,
 count(*) FILTER(WHERE q_rating_zero) rows_with_zero
FROM feedback GROUP BY month;
"""
