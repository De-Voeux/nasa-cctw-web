-- A daily cap on assistant questions, counted in the database so it is exact across Worker instances.
--
-- rag_usage_hit('ask', 100) adds one to today's count (UTC day) and says whether that question may
-- run. It is a single INSERT ... ON CONFLICT DO UPDATE ... WHERE n < limit, so two questions arriving
-- together cannot both take the last place. Counts only questions that reach the model; greetings and
-- thanks are answered without one and are not counted.
--
-- Why UTC: the Workers AI free allocation resets at 00:00 UTC.

begin;

create table if not exists rag.usage (
  day   date not null,
  scope text not null,
  n     int  not null default 0 check (n >= 0),
  primary key (day, scope)
);
alter table rag.usage enable row level security;
revoke all on rag.usage from public, anon, authenticated;

create or replace function public.rag_usage_hit(p_scope text, p_limit int)
returns table (allowed boolean, used int)
language plpgsql security definer
set search_path = rag, pg_temp
as $$
declare
  v_day  date := (now() at time zone 'utc')::date;
  v_used int;
begin
  if p_limit <= 0 then
    return query select false, 0;
    return;
  end if;
  insert into rag.usage as u (day, scope, n) values (v_day, p_scope, 1)
  on conflict (day, scope) do update set n = u.n + 1 where u.n < p_limit
  returning u.n into v_used;
  if v_used is null then
    -- the cap is reached: nothing was added
    select n into v_used from rag.usage where day = v_day and scope = p_scope;
    return query select false, v_used;
  else
    return query select true, v_used;
  end if;
end
$$;

revoke all on function public.rag_usage_hit(text, int) from public, anon, authenticated;
grant execute on function public.rag_usage_hit(text, int) to service_role;

commit;

-- rollback:
-- drop function if exists public.rag_usage_hit(text, int);
-- drop table if exists rag.usage;
