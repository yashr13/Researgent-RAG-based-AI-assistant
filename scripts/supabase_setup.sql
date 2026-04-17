-- Run this once in the Supabase SQL Editor.
-- It prepares Postgres, pgvector, app tables, and the storage bucket.

create schema if not exists extensions;
create extension if not exists vector with schema extensions;

create table if not exists public.projects (
  id bigserial primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  project_key text not null,
  created_at text not null
);

alter table public.projects
  add column if not exists user_id uuid references auth.users(id) on delete cascade;

alter table public.projects
  drop constraint if exists projects_project_key_key;

create unique index if not exists idx_projects_user_project_key
  on public.projects(user_id, project_key);

create table if not exists public.documents (
  id bigserial primary key,
  project_id bigint not null references public.projects(id) on delete cascade,
  filename text not null,
  filepath text not null,
  uploaded_at text not null,
  source_type text not null default 'local',
  external_id text,
  title text,
  authors_json text not null default '[]',
  abstract text,
  url text,
  published_at text,
  storage_url text
);

alter table public.documents add column if not exists source_type text default 'local';
alter table public.documents add column if not exists external_id text;
alter table public.documents add column if not exists title text;
alter table public.documents add column if not exists authors_json text default '[]';
alter table public.documents add column if not exists abstract text;
alter table public.documents add column if not exists url text;
alter table public.documents add column if not exists published_at text;
alter table public.documents add column if not exists storage_url text;

create table if not exists public.chats (
  id bigserial primary key,
  project_id bigint not null references public.projects(id) on delete cascade,
  title text,
  created_at text not null
);

create table if not exists public.messages (
  id bigserial primary key,
  chat_id bigint not null references public.chats(id) on delete cascade,
  role text not null,
  content text not null,
  sources_json text not null default '[]',
  created_at text not null
);

create table if not exists public.document_chunks (
  id bigserial primary key,
  project_key text not null,
  document_id bigint,
  chunk_index integer not null,
  content text not null,
  source text,
  filename text,
  page integer,
  section_title text,
  metadata_json text not null default '{}',
  embedding extensions.vector(1536) not null
);

create index if not exists idx_projects_project_key
  on public.projects(project_key);

create index if not exists idx_projects_user_id
  on public.projects(user_id);

create index if not exists idx_documents_project_id
  on public.documents(project_id);

create index if not exists idx_chats_project_id
  on public.chats(project_id);

create index if not exists idx_messages_chat_id
  on public.messages(chat_id);

create index if not exists idx_document_chunks_project_key
  on public.document_chunks(project_key);

create index if not exists idx_document_chunks_document_id
  on public.document_chunks(document_id);

insert into storage.buckets (id, name, public)
values ('documents', 'documents', false)
on conflict (id) do nothing;
