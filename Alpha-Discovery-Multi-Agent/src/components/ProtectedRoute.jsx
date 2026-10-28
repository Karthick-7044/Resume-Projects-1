import React from 'react';
import { useAuth } from '@/context/AuthContext';
import { Button } from '@/components/ui/button';
import { Lock, ShieldAlert } from 'lucide-react';

export function ProtectedRoute({ children, onOpenAuth }) {
  const { user, loading, isConfigured, signInDemo } = useAuth();

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[300px] w-full">
        <div className="flex items-center gap-3 px-5 py-3 rounded-full bg-void-850 border border-white/10 text-xs font-mono text-cyan-300 backdrop-blur-md">
          <span className="w-4 h-4 rounded-full border-2 border-cyan-400 border-t-transparent animate-spin" />
          <span>Authenticating Session...</span>
        </div>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="glass-card rounded-3xl p-8 sm:p-12 border border-white/10 text-center max-w-xl mx-auto space-y-6">
        <div className="w-16 h-16 rounded-full bg-blue-950/60 border border-blue-500/30 text-blue-400 flex items-center justify-center mx-auto shadow-glow-blue">
          <Lock className="w-8 h-8" />
        </div>
        <div className="space-y-2">
          <h3 className="font-heading text-2xl font-bold text-white">
            Restricted Research Workspace
          </h3>
          <p className="text-sm text-slate-300 leading-relaxed">
            Access to live factor stream diagnostics, regime backtest signals, and model parameters requires an authenticated research session.
          </p>
        </div>

        <div className="flex flex-col sm:flex-row items-center justify-center gap-3 pt-2">
          <Button
            variant="default"
            onClick={() => onOpenAuth('signin')}
            className="w-full sm:w-auto bg-gradient-to-r from-blue-600 to-purple-600 text-white"
          >
            Sign in to Workspace
          </Button>
          <Button
            variant="secondary"
            onClick={() => onOpenAuth('register')}
            className="w-full sm:w-auto"
          >
            Register Account
          </Button>
          <Button
            variant="outline"
            onClick={signInDemo}
            className="w-full sm:w-auto border-blue-500/40 text-cyan-300 hover:bg-blue-950/40 font-mono text-xs"
          >
            Guest Demo Mode
          </Button>
        </div>
      </div>
    );
  }

  return children;
}
