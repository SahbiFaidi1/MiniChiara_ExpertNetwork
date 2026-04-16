-- Expert Network MVP schema (Supabase Postgres compatible)

-- Required for gen_random_uuid()
create extension if not exists pgcrypto;

-- Recommended for semantic search
-- If this fails in your environment, you can comment it out and use the float-array fallback noted below.
create extension if not exists vector;

-- People table (source of truth)
create table if not exists public.people (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  "current_role" text,
  company text,
  location text,
  expertise_tags text[] not null default '{}'::text[],
  who_knows_them text[] not null default '{}'::text[],
  background text,
  notes text,
  searchable_text text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists people_name_idx on public.people (lower(name));
create index if not exists people_company_idx on public.people (lower(company));

-- Keep updated_at fresh
create or replace function public.set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists people_set_updated_at on public.people;
create trigger people_set_updated_at
before update on public.people
for each row execute function public.set_updated_at();

-- Embeddings table
-- Preferred (pgvector):
create table if not exists public.person_embeddings (
  person_id uuid primary key references public.people(id) on delete cascade,
  embedding vector(1536) not null,
  embedding_model text not null default 'text-embedding-3-small',
  created_at timestamptz not null default now()
);

-- ANN index: only create once you have >1000 rows; set lists ≈ sqrt(row_count).
-- For MVP with <1000 rows, exact scan is fast enough.
-- create index if not exists person_embeddings_ivfflat_idx
-- on public.person_embeddings
-- using ivfflat (embedding vector_cosine_ops)
-- with (lists = 100);

-- Fallback if pgvector is unavailable:
-- 1) drop person_embeddings table above
-- 2) create a float-array table instead:
--    create table public.person_embeddings (
--      person_id uuid primary key references public.people(id) on delete cascade,
--      embedding float4[] not null,
--      embedding_model text not null default 'text-embedding-3-small',
--      created_at timestamptz not null default now()
--    );
-- The Python MVP supports both based on USE_PGVECTOR=true/false.

