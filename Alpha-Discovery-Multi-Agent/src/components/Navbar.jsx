import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Menu, X, ShieldCheck, UserCheck, ArrowUpRight, LogOut, User } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/context/AuthContext';
import { Link, useRouter } from '@/lib/router';

export function Navbar({ onOpenAuth }) {
  const { user, profile, signOut } = useAuth();
  const [scrolled, setScrolled] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const userName = profile?.full_name?.split(' ')[0] || user?.user_metadata?.full_name?.split(' ')[0] || user?.email?.split('@')[0] || 'User';

  useEffect(() => {
    const handleScroll = () => {
      if (window.scrollY > 20) {
        setScrolled(true);
      } else {
        setScrolled(false);
      }
    };
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  const { path } = useRouter();
  const navLinks = [
    { name: 'Home', href: '/' },
    { name: 'Company', href: '/company' },
    { name: 'Services', href: '/services' },
    { name: 'Workspace', href: '/workspace' },
    { name: 'Contact', href: '/contact' },
  ];
  const handleNavClick = () => setMobileMenuOpen(false);

  return (
    <motion.header
      initial={{ y: -50, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
      className="fixed top-3 sm:top-5 inset-x-0 mx-auto z-50 w-[calc(100%-1.5rem)] max-w-6xl transition-all duration-300"
    >
      <div
        className={`relative flex items-center justify-between gap-5 rounded-2xl sm:rounded-full px-4 sm:px-5 py-3 transition-all duration-300 ${
          scrolled
            ? 'bg-[#050505]/90 backdrop-blur-2xl border border-white/15 shadow-2xl shadow-black/80'
            : 'bg-[#050505]/65 backdrop-blur-xl border border-white/10 shadow-xl'
        }`}
      >
        {/* Brand / Logo */}
        <Link to="/" className="flex min-w-0 items-center gap-3 group">
          <div className="relative flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-blue-600/30 via-indigo-600/20 to-purple-600/30 border border-blue-500/40 group-hover:border-blue-400 transition-colors shadow-inner">
            <span className="font-heading font-extrabold text-xl text-white group-hover:scale-110 transition-transform">
              α
            </span>
            <div className="absolute inset-0 rounded-full bg-blue-500/20 blur-md opacity-0 group-hover:opacity-100 transition-opacity" />
          </div>
          <div className="flex min-w-0 flex-col">
            <span className="truncate font-heading font-bold text-[14px] sm:text-base tracking-tight text-white group-hover:text-blue-300 transition-colors">
              Multi-Agent Alpha Discovery
            </span>
            <span className="hidden xl:block text-[10px] font-mono tracking-widest text-blue-400/80 uppercase -mt-0.5">
              Autonomous Quantitative AI
            </span>
          </div>
        </Link>

        {/* Desktop Nav Links */}
        <nav className="hidden lg:flex items-center gap-1 rounded-full border border-white/[0.08] bg-black/20 px-2 py-1 backdrop-blur-md">
          {navLinks.map((link) => (
            <Link
              key={link.name}
              to={link.href}
              aria-current={path === link.href ? 'page' : undefined}
              className={`px-3.5 py-2 text-sm font-medium rounded-full transition-all duration-200 ${path === link.href ? 'bg-white text-black' : 'text-slate-300 hover:text-white hover:bg-white/[0.07]'}`}
            >
              {link.name}
            </Link>
          ))}
        </nav>

        {/* Desktop Action Buttons */}
        <div className="hidden lg:flex items-center gap-2">
          {user ? (
            <>
              <Link
                to="/workspace"
                className="flex items-center gap-2 px-4 py-1.5 rounded-full bg-blue-950/60 border border-blue-500/40 text-xs font-mono text-cyan-300 hover:bg-blue-900/60 transition-colors"
              >
                <User className="w-3.5 h-3.5 text-cyan-400" />
                <span>Hi, {userName}</span>
              </Link>
              <Button
                variant="secondary"
                size="sm"
                onClick={signOut}
                className="text-xs border-rose-500/30 text-rose-300 hover:text-white hover:bg-rose-950/40"
              >
                <LogOut className="w-3.5 h-3.5 mr-1" />
                Sign out
              </Button>
            </>
          ) : (
            <>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onOpenAuth('signin')}
                className="text-slate-300 hover:text-white hover:bg-white/5 text-sm px-3.5"
              >
                Sign in
              </Button>
              <Button
                variant="default"
                size="sm"
                onClick={() => onOpenAuth('register')}
                className="bg-gradient-to-r from-blue-600 to-purple-600 text-white hover:from-blue-500 hover:to-purple-500 border border-blue-400/30 text-sm shadow-glow-blue"
              >
                <UserCheck className="w-4 h-4 mr-1.5 opacity-90" />
                Register
              </Button>
            </>
          )}
        </div>

        {/* Mobile Hamburger Toggle */}
        <div className="flex items-center gap-2 lg:hidden">
          {user ? (
            <Button
              variant="secondary"
              size="sm"
              onClick={signOut}
              className="text-xs px-2.5 py-1 h-8 rounded-full border-rose-500/30 text-rose-300"
            >
              Sign out
            </Button>
          ) : (
            <Button
              variant="default"
              size="sm"
              onClick={() => onOpenAuth('register')}
              className="bg-blue-600/90 text-white text-xs px-3 py-1 h-8 rounded-full"
            >
              Register
            </Button>
          )}
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="p-2 text-slate-300 hover:text-white rounded-full hover:bg-white/10 transition-colors"
            aria-label="Toggle Navigation Menu"
          >
            {mobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
          </button>
        </div>
      </div>

      {/* Mobile Drawer Menu */}
      <AnimatePresence>
        {mobileMenuOpen && (
          <motion.div
            initial={{ opacity: 0, y: -10, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -10, scale: 0.98 }}
            transition={{ duration: 0.2 }}
            className="lg:hidden mt-3 rounded-2xl bg-[#09090b]/95 backdrop-blur-2xl border border-white/10 p-5 shadow-2xl space-y-4"
          >
            <div className="flex flex-col space-y-2">
              {navLinks.map((link) => (
                <Link
                  key={link.name}
                  to={link.href}
                  onClick={handleNavClick}
                  className="px-4 py-2.5 text-base font-medium text-slate-200 hover:text-white hover:bg-white/5 rounded-xl transition-colors flex items-center justify-between"
                >
                  <span>{link.name}</span>
                  <ArrowUpRight className="w-4 h-4 opacity-50" />
                </Link>
              ))}
            </div>

            <div className="pt-3 border-t border-white/10 flex flex-col gap-2.5">
              <Button
                variant="secondary"
                onClick={() => {
                  setMobileMenuOpen(false);
                  onOpenAuth('signin');
                }}
                className="w-full justify-center"
              >
                Sign in
              </Button>
              <Button
                variant="default"
                onClick={() => {
                  setMobileMenuOpen(false);
                  onOpenAuth('register');
                }}
                className="w-full justify-center bg-gradient-to-r from-blue-600 to-purple-600 text-white"
              >
                Create Research Account
              </Button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.header>
  );
}
