-- Example semantic views for Phase 2 (implement in your solution repo).
-- Required tools must query these views, not raw reservations_hackathon.

create or replace view public.vw_stay_night_base as
select
  r.*
from public.reservations_hackathon r
where r.reservation_status <> 'Cancelled'
  and r.financial_status = 'Posted';

-- Posted universe WITHOUT the non-cancelled filter, so agent-facing tools never
-- read reservations_hackathon directly. Serves the "include cancelled" universe
-- (get_otb_summary exclude_cancelled=False) and the point-in-time rebuild
-- (get_as_of_otb), which both need cancelled rows + cancellation_datetime.
create or replace view public.vw_stay_night_posted as
select
  r.*
from public.reservations_hackathon r
where r.financial_status = 'Posted';

-- Posted + Provisional (tentative) business, all reservation statuses. Serves the
-- explicit include-provisional path (get_otb_summary include_provisional=True); the
-- tool applies the cancelled filter on top. Lets that path read a view, never the
-- raw fact table.
create or replace view public.vw_stay_night_with_provisional as
select
  r.*
from public.reservations_hackathon r
where r.financial_status in ('Posted', 'Provisional');

create or replace view public.vw_segment_stay_night as
select
  b.*,
  coalesce(h.macro_group, m.macro_group) as effective_macro_group,
  m.market_name
from public.vw_stay_night_base b
join public.market_code_lookup m on m.market_code = b.market_code
left join lateral (
  select h.macro_group
  from public.market_macro_group_history h
  where h.market_code = b.market_code
    and b.stay_date >= h.valid_from
    and (h.valid_to is null or b.stay_date < h.valid_to)
  order by h.valid_from desc
  limit 1
) h on true;
