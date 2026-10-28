import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Lock, Mail, User, ShieldCheck, AlertCircle, CheckCircle2, KeyRound, ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useAuth } from '@/context/AuthContext';

export function AuthModal({ isOpen, onClose, initialMode = 'signin' }) {
  const { signIn, signUp, signInWithGoogle, resetPassword, isConfigured } = useAuth();

  const [mode, setMode] = useState(initialMode); // 'signin' | 'register' | 'forgot'
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');

  const [errorMsg, setErrorMsg] = useState('');
  const [successMsg, setSuccessMsg] = useState('');
  const [loading, setLoading] = useState(false);

  React.useEffect(() => {
    setMode(initialMode);
    setErrorMsg('');
    setSuccessMsg('');
    setEmail('');
    setPassword('');
    setName('');
    setConfirmPassword('');
  }, [initialMode, isOpen]);

  if (!isOpen) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMsg('');
    setSuccessMsg('');

    // Field validations
    if (!email || (mode !== 'forgot' && !password)) {
      setErrorMsg('Please fill in all required fields.');
      return;
    }

    if (mode === 'register') {
      if (!name) {
        setErrorMsg('Please enter your full name.');
        return;
      }
      if (password !== confirmPassword) {
        setErrorMsg('Passwords do not match.');
        return;
      }
      if (password.length < 6) {
        setErrorMsg('Password must be at least 6 characters.');
        return;
      }
    }

    setLoading(true);

    try {
      if (mode === 'signin') {
        await signIn({ email, password });
        setSuccessMsg('Signed in. Opening workspace...');
        setTimeout(() => {
          onClose();
        }, 1000);
      } else if (mode === 'register') {
        await signUp({ email, password, fullName: name });
        setSuccessMsg('Account created. You can sign in once email confirmation is complete.');
        setTimeout(() => {
          onClose();
        }, 1200);
      } else if (mode === 'forgot') {
        await resetPassword(email);
        setSuccessMsg('Password reset instructions transmitted to your email.');
      }
    } catch (err) {
      console.error('Auth error:', err);
      // Format friendly error messages
      const msg = err.message || '';
      if (msg.includes('Invalid login credentials')) {
        setErrorMsg('Invalid email or password. Please verify your credentials.');
      } else if (msg.includes('User already registered') || msg.includes('already exists')) {
        setErrorMsg('An account with this email address already exists. Try signing in.');
      } else if (msg.includes('rate limit')) {
        setErrorMsg('Security rate limit exceeded. Please wait a moment and try again.');
      } else {
        setErrorMsg(msg || 'An error occurred during authentication.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 overflow-y-auto">
        {/* Backdrop overlay */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
          className="fixed inset-0 bg-black/80 backdrop-blur-md"
        />

        {/* Modal Window Container */}
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 15 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 15 }}
          transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
          className="relative w-full max-w-md bg-void-900 border border-white/15 rounded-3xl p-7 sm:p-8 shadow-2xl z-10 overflow-hidden"
        >
          {/* Top Radial Glow */}
          <div className="absolute top-0 inset-x-0 h-1 bg-gradient-to-r from-blue-500 via-indigo-500 to-purple-500" />
          <div className="absolute top-0 right-0 w-40 h-40 bg-blue-600/10 rounded-full blur-3xl pointer-events-none" />

          {/* Close Button */}
          <button
            onClick={onClose}
            className="absolute top-5 right-5 p-2 rounded-full text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>

          {/* Institutional Header */}
          <div className="space-y-2 mb-6">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-950/60 border border-blue-500/30 text-[11px] font-mono text-cyan-300">
              <ShieldCheck className="w-3.5 h-3.5 text-cyan-400" />
              <span>Account access</span>
            </div>
            <h3 className="font-heading text-2xl font-bold text-white">
              {mode === 'signin'
                ? 'Sign in to Workspace'
                : mode === 'register'
                ? 'Register Research Account'
                : 'Reset Password'}
            </h3>
            <p className="text-xs text-slate-400">
              Access your quantitative research workspace.
            </p>
          </div>

          {/* Error & Success Feedback Banners */}
          {errorMsg && (
            <motion.div
              initial={{ opacity: 0, y: -5 }}
              animate={{ opacity: 1, y: 0 }}
              className="mb-4 p-3 rounded-xl bg-rose-950/50 border border-rose-500/40 text-rose-200 text-xs flex items-center gap-2"
            >
              <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
              <span>{errorMsg}</span>
            </motion.div>
          )}

          {successMsg && (
            <motion.div
              initial={{ opacity: 0, y: -5 }}
              animate={{ opacity: 1, y: 0 }}
              className="mb-4 p-3 rounded-xl bg-emerald-950/50 border border-emerald-500/40 text-emerald-200 text-xs flex items-center gap-2"
            >
              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
              <span>{successMsg}</span>
            </motion.div>
          )}

          {isConfigured && (
            <div className="space-y-3">
              <button
                type="button"
                onClick={async () => { try { await signInWithGoogle(); } catch (e) { setErrorMsg(e.message); } }}
                className="w-full flex items-center justify-center gap-3 rounded-full bg-white text-black font-medium h-11 hover:bg-indigo-100 transition-colors"
              >
                <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true"><path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9.1 3.6l6.8-6.8C35.8 2.4 30.3 0 24 0 14.6 0 6.5 5.4 2.6 13.2l7.9 6.1C12.4 13.6 17.7 9.5 24 9.5z"/><path fill="#4285F4" d="M46.5 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.7c-.6 3-2.3 5.5-4.8 7.2l7.5 5.8c4.4-4.1 7.1-10.1 7.1-17.5z"/><path fill="#FBBC05" d="M10.5 28.7c-.5-1.5-.8-3-.8-4.7s.3-3.2.8-4.7l-7.9-6.1C.9 16.4 0 20.100 0 24s.9 7.600 2.600 10.800l7.900-6.100z"/><path fill="#34A853" d="M24 48c6.500 0 12-2.100 16-5.800l-7.500-5.800c-2.100 1.400-4.800 2.300-8.500 2.300-6.300 0-11.600-4.100-13.500-9.800l-7.900 6.100C6.500 42.600 14.600 48 24 48z"/></svg>
                Continue with Google
              </button>
              <div className="text-center text-xs text-slate-500">or use your email</div>
            </div>
          )}
          <form onSubmit={handleSubmit} className="space-y-4">
            {mode === 'register' && (
              <div className="space-y-1.5">
                <label className="text-[11px] font-mono text-slate-300 uppercase">
                  Full Name *
                </label>
                <div className="relative">
                  <Input
                    required
                    type="text"
                    placeholder="Karthick"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className="pl-10"
                  />
                  <User className="w-4 h-4 text-slate-400 absolute left-3.5 top-3.5" />
                </div>
              </div>
            )}

            <div className="space-y-1.5">
              <label className="text-[11px] font-mono text-slate-300 uppercase">
                Email Address *
              </label>
              <div className="relative">
                <Input
                  required
                  type="email"
                  placeholder="karthick@quant.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="pl-10"
                />
                <Mail className="w-4 h-4 text-slate-400 absolute left-3.5 top-3.5" />
              </div>
            </div>

            {mode !== 'forgot' && (
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <label className="text-[11px] font-mono text-slate-300 uppercase">
                    Password *
                  </label>
                  {mode === 'signin' && (
                    <button
                      type="button"
                      onClick={() => setMode('forgot')}
                      className="text-[11px] text-blue-400 hover:text-blue-300 hover:underline"
                    >
                      Forgot password?
                    </button>
                  )}
                </div>
                <div className="relative">
                  <Input
                    required
                    type="password"
                    placeholder="••••••••••••"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="pl-10"
                  />
                  <Lock className="w-4 h-4 text-slate-400 absolute left-3.5 top-3.5" />
                </div>
              </div>
            )}

            {mode === 'register' && (
              <div className="space-y-1.5">
                <label className="text-[11px] font-mono text-slate-300 uppercase">
                  Confirm Password *
                </label>
                <div className="relative">
                  <Input
                    required
                    type="password"
                    placeholder="••••••••••••"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    className="pl-10"
                  />
                  <Lock className="w-4 h-4 text-slate-400 absolute left-3.5 top-3.5" />
                </div>
              </div>
            )}

            <Button
              type="submit"
              disabled={loading}
              variant="default"
              className="w-full bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 text-white font-semibold py-3 mt-2 shadow-glow-blue"
            >
              {loading ? (
                <span className="flex items-center gap-2 justify-center">
                  <span className="w-4 h-4 rounded-full border-2 border-white border-t-transparent animate-spin" />
                  Authenticating...
                </span>
              ) : mode === 'signin' ? (
                'Sign in'
              ) : mode === 'register' ? (
                'Create Research Account'
              ) : (
                'Send Password Reset Link'
              )}
            </Button>

            {/* Toggle Mode Footer */}
            <div className="text-center pt-3 border-t border-white/10 space-y-1">
              {mode === 'signin' && (
                <p className="text-xs text-slate-400">
                  Don't have an account?{' '}
                  <button
                    type="button"
                    onClick={() => {
                      setMode('register');
                      setErrorMsg('');
                    }}
                    className="text-blue-400 hover:text-blue-300 font-semibold underline underline-offset-2 ml-1"
                  >
                    Register
                  </button>
                </p>
              )}

              {mode === 'register' && (
                <p className="text-xs text-slate-400">
                  Already have an account?{' '}
                  <button
                    type="button"
                    onClick={() => {
                      setMode('signin');
                      setErrorMsg('');
                    }}
                    className="text-blue-400 hover:text-blue-300 font-semibold underline underline-offset-2 ml-1"
                  >
                    Sign in
                  </button>
                </p>
              )}

              {mode === 'forgot' && (
                <p className="text-xs text-slate-400">
                  Remembered your password?{' '}
                  <button
                    type="button"
                    onClick={() => {
                      setMode('signin');
                      setErrorMsg('');
                    }}
                    className="text-blue-400 hover:text-blue-300 font-semibold underline underline-offset-2 ml-1"
                  >
                    Back to Sign in
                  </button>
                </p>
              )}
            </div>
          </form>

        </motion.div>
      </div>
    </AnimatePresence>
  );
}
