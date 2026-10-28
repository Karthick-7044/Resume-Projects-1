import React, { createContext, useContext, useState, useEffect } from 'react';
import { supabase, isSupabaseConfigured } from '@/lib/supabase';

const AuthContext = createContext({
  user: null,
  profile: null,
  session: null,
  loading: true,
  signUp: async () => {},
  signIn: async () => {},
  signOut: async () => {},
  resetPassword: async () => {},
  isConfigured: false,
});

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [profile, setProfile] = useState(null);
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchProfile = async (userId) => {
    if (!userId || !isSupabaseConfigured()) return null;
    try {
      const { data, error } = await supabase
        .from('profiles')
        .select('*')
        .eq('user_id', userId)
        .single();

      if (error && error.code !== 'PGRST116') {
        console.warn('Error fetching profile:', error.message);
      }
      if (data) {
        setProfile(data);
        return data;
      }
    } catch (err) {
      console.error('Fetch profile exception:', err);
    }
    return null;
  };

  useEffect(() => {
    // Initialize session and listen to changes
    const getInitialSession = async () => {
      if (!isSupabaseConfigured()) {
        setLoading(false);
        return;
      }

      try {
        const { data: { session: currentSession }, error } = await supabase.auth.getSession();
        if (error) throw error;
        setSession(currentSession);
        setUser(currentSession?.user ?? null);

        if (currentSession?.user) {
          await fetchProfile(currentSession.user.id);
        }
      } catch (err) {
        console.error('Session initialization error:', err);
      } finally {
        setLoading(false);
      }
    };

    getInitialSession();

    if (isSupabaseConfigured()) {
      const { data: { subscription } } = supabase.auth.onAuthStateChange(async (event, newSession) => {
        setSession(newSession);
        setUser(newSession?.user ?? null);

        if (newSession?.user) {
          await fetchProfile(newSession.user.id);
        } else {
          setProfile(null);
        }
        setLoading(false);
      });

      return () => {
        subscription?.unsubscribe();
      };
    }
  }, []);

  const signUp = async ({ email, password, fullName }) => {
    if (!isSupabaseConfigured()) {
      throw new Error('Supabase credentials are not configured in .env. Please set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY.');
    }

    // 1. Register Auth User
    const { data, error } = await supabase.auth.signUp({
      email,
      password,
      options: {
        data: {
          full_name: fullName,
        },
      },
    });

    if (error) throw error;

    // 2. Insert Profile into PostgreSQL `profiles` table
    if (data?.user) {
      const { error: profileError } = await supabase
        .from('profiles')
        .insert([
          {
            user_id: data.user.id,
            full_name: fullName,
            email: email,
          },
        ]);

      if (profileError) {
        console.warn('Profile creation note:', profileError.message);
      }

      setProfile({
        user_id: data.user.id,
        full_name: fullName,
        email: email,
        created_at: new Date().toISOString(),
      });
    }

    return data;
  };

  const signIn = async ({ email, password }) => {
    if (!isSupabaseConfigured()) {
      throw new Error('Supabase credentials are not configured in .env. Please set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY.');
    }

    const { data, error } = await supabase.auth.signInWithPassword({
      email,
      password,
    });

    if (error) throw error;
    if (data?.user) {
      await fetchProfile(data.user.id);
    }
    return data;
  };

  const signOut = async () => {
    if (!isSupabaseConfigured()) {
      setUser(null);
      setProfile(null);
      setSession(null);
      return;
    }
    const { error } = await supabase.auth.signOut();
    if (error) throw error;
    setUser(null);
    setProfile(null);
    setSession(null);
  };

  const resetPassword = async (email) => {
    if (!isSupabaseConfigured()) {
      throw new Error('Supabase credentials are not configured in .env. Please set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY.');
    }

    const { data, error } = await supabase.auth.resetPasswordForEmail(email, {
      redirectTo: `${window.location.origin}/`,
    });

    if (error) throw error;
    return data;
  };

  const signInDemo = () => {
    const demoUser = {
      id: 'demo-researcher-01',
      email: 'quant.analyst@rajsalpha.com',
      user_metadata: { full_name: 'Lead Alpha Researcher' },
    };
    const demoProfile = {
      user_id: 'demo-researcher-01',
      full_name: 'Lead Alpha Researcher',
      email: 'quant.analyst@rajsalpha.com',
      role: 'Institutional Quant',
      created_at: new Date().toISOString(),
    };
    setUser(demoUser);
    setProfile(demoProfile);
    setSession({ user: demoUser });
  };

  const value = {
    user,
    profile,
    session,
    loading,
    signUp,
    signIn,
    signInDemo,
    signOut,
    resetPassword,
    isConfigured: isSupabaseConfigured(),
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
