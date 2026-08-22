import React, { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import { Session, User } from '@supabase/supabase-js';
import { supabase } from '../lib/supabase';

export type AuthMode = 'signin' | 'signup' | 'forgot_password' | 'reset_password' | 'verify_email';

interface AuthContextType {
  session: Session | null;
  user: User | null;
  loading: boolean;
  isEmailVerified: boolean;
  authMode: AuthMode;
  setAuthMode: (mode: AuthMode) => void;
  unverifiedEmail: string | null;
  setUnverifiedEmail: (email: string | null) => void;
  authError: string | null;
  setAuthError: (error: string | null) => void;
  signInWithGoogle: () => Promise<{ error: Error | null }>;
  signOut: () => Promise<{ error: Error | null }>;
  resendVerificationEmail: (email: string) => Promise<{ error: Error | null }>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [session, setSession] = useState<Session | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [authMode, setAuthMode] = useState<AuthMode>('signin');
  const [unverifiedEmail, setUnverifiedEmail] = useState<string | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    // 1. Detect OAuth error parameters in URL hash or query string
    const hash = window.location.hash;
    const search = window.location.search;
    const searchParams = new URLSearchParams(search);
    let errorDesc = searchParams.get('error_description') || searchParams.get('error');

    if (!errorDesc && hash) {
      const hashParams = new URLSearchParams(hash.substring(1));
      errorDesc = hashParams.get('error_description') || hashParams.get('error');
    }

    if (errorDesc) {
      const cleanError = decodeURIComponent(errorDesc.replace(/\+/g, ' '));
      console.warn('Supabase OAuth Error:', cleanError);
      setAuthError(cleanError);
      // Clean up error params from browser URL bar
      window.history.replaceState(null, '', window.location.pathname);
    }

    // 2. Check existing active session
    supabase.auth.getSession().then(({ data: { session }, error }) => {
      if (isMounted) {
        if (error) {
          console.error('Failed to retrieve session:', error);
          setAuthError(error.message);
        }
        setSession(session);
        setUser(session?.user ?? null);
        setLoading(false);
      }
    });

    // 3. Listen for auth changes (sign in, sign out, token refresh)
    const { data: { subscription } } = supabase.auth.onAuthStateChange((event, session) => {
      if (isMounted) {
        setSession(session);
        setUser(session?.user ?? null);
        setLoading(false);

        // Clean up URL hash / code query string after successful login
        if (session && (event === 'SIGNED_IN' || event === 'TOKEN_REFRESHED')) {
          setAuthError(null);
          if (window.location.hash || window.location.search.includes('code=')) {
            window.history.replaceState(null, '', window.location.pathname);
          }
        }
      }
    });

    return () => {
      isMounted = false;
      subscription.unsubscribe();
    };
  }, []);

  // Determine if current user has a verified email or is OAuth / Google authenticated
  const isEmailVerified = Boolean(
    user && (
      Boolean(user.email_confirmed_at) ||
      Boolean((user as any).confirmed_at) ||
      user.app_metadata?.provider === 'google' ||
      user.app_metadata?.provider === 'oauth' ||
      user.app_metadata?.providers?.includes('google') ||
      user.user_metadata?.email_verified === true ||
      Boolean(user.identities && user.identities.some((id: any) => id.provider === 'google'))
    )
  );

  const signInWithGoogle = async () => {
    setAuthError(null);
    const redirectTo = `${window.location.origin}`;
    const { error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo,
        queryParams: {
          access_type: 'offline',
          prompt: 'consent',
        },
      },
    });
    if (error) {
      setAuthError(error.message);
    }
    return { error: error ? new Error(error.message) : null };
  };

  const signOut = async () => {
    const { error } = await supabase.auth.signOut();
    if (!error) {
      setSession(null);
      setUser(null);
      setAuthMode('signin');
      setAuthError(null);
    }
    return { error: error ? new Error(error.message) : null };
  };

  const resendVerificationEmail = async (email: string) => {
    const { error } = await supabase.auth.resend({
      type: 'signup',
      email,
      options: {
        emailRedirectTo: `${window.location.origin}`,
      },
    });
    return { error: error ? new Error(error.message) : null };
  };

  return (
    <AuthContext.Provider
      value={{
        session,
        user,
        loading,
        isEmailVerified,
        authMode,
        setAuthMode,
        unverifiedEmail,
        setUnverifiedEmail,
        authError,
        setAuthError,
        signInWithGoogle,
        signOut,
        resendVerificationEmail,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
