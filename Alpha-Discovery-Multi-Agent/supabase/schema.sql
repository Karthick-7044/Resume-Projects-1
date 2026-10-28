-- ======================================================
-- Multi-Agent Alpha Discovery — Supabase PostgreSQL Schema
-- ======================================================

-- 1. Create Profiles Table
create table if not exists public.profiles (
  id uuid default gen_random_uuid() primary key,
  user_id uuid references auth.users(id) on delete cascade not null unique,
  full_name text not null,
  email text not null,
  created_at timestamp with time zone default timezone('utc'::text, now()) not null
);

-- 2. Enable Row Level Security (RLS)
alter table public.profiles enable row level security;

-- 3. RLS Policies
-- Allow users to view profiles
create policy "Public profiles are viewable by everyone"
  on public.profiles for select
  using (true);

-- Allow authenticated users to insert their own profile row
create policy "Users can insert their own profile"
  on public.profiles for insert
  with check (auth.uid() = user_id);

-- Allow users to update their own profile
create policy "Users can update own profile"
  on public.profiles for update
  using (auth.uid() = user_id);

-- 4. Indices for Performance
create index if not exists profiles_user_id_idx on public.profiles(user_id);
create index if not exists profiles_email_idx on public.profiles(email);
