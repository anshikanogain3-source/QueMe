import { createClient } from "@supabase/supabase-js";

const url = import.meta.env.VITE_SUPABASE_URL;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

// Never silently fall back to a fake identity when Supabase is not configured.
export const supabase = url && anonKey
  ? createClient(url, anonKey, {
    auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
  })
  : null;

export function requireSupabase() {
  if (!supabase) {
    throw new Error("Authentication is not configured. Set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY.");
  }
  return supabase;
}
