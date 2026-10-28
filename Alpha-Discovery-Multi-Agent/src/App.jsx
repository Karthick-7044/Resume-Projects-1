import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { Router, useRouter } from '@/lib/router';
import { AuthProvider } from '@/context/AuthContext';
import { Navbar } from '@/components/Navbar';
import { Hero } from '@/components/Hero';
import { Company } from '@/components/Company';
import { ResearchNetwork } from '@/components/ResearchNetwork';
import { Services } from '@/components/Services';
import { Contact } from '@/components/Contact';
import { ProtectedRoute } from '@/components/ProtectedRoute';
import { WorkspaceSection } from '@/components/WorkspaceSection';
import { Footer } from '@/components/Footer';
import { AuthModal } from '@/components/AuthModal';
import { Aurora, ScrollProgress, Ticker, WaveDivider, KeyNumbers, TICKER_ITEMS } from '@/components/motion';

function Page({ children }) {
  return (
    <motion.div className="rest min-h-[70vh]" initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}>
      {children}
    </motion.div>
  );
}

function MainAppContent() {
  const { path, navigate } = useRouter();
  const [authModalOpen, setAuthModalOpen] = useState(false);
  const [authMode, setAuthMode] = useState('signin');

  const handleOpenAuth = (mode = 'signin') => {
    setAuthMode(mode);
    setAuthModalOpen(true);
  };

  let page;
  if (path === '/company') {
    page = <Page><Company /><WaveDivider /><ResearchNetwork /></Page>;
  } else if (path === '/services') {
    page = <Page><Services /></Page>;
  } else if (path === '/workspace') {
    page = <Page><ProtectedRoute onOpenAuth={handleOpenAuth}><WorkspaceSection /></ProtectedRoute></Page>;
  } else if (path === '/contact') {
    page = <Page><Contact /></Page>;
  } else {
    page = (
      <>
        <Hero onExploreClick={() => navigate('/company')} onContactClick={() => navigate('/contact')} />
        <div className="rest">
          <Ticker items={TICKER_ITEMS} />
          <KeyNumbers />
          <WaveDivider />
        </div>
      </>
    );
  }

  return (
    <div className="relative min-h-screen bg-[#07070b] text-slate-100 font-sans selection:bg-indigo-500/30 selection:text-indigo-100">
      <ScrollProgress />
      <Aurora />
      <Navbar onOpenAuth={handleOpenAuth} />
      <main key={path}>{page}</main>
      <Footer />
      <AuthModal isOpen={authModalOpen} onClose={() => setAuthModalOpen(false)} initialMode={authMode} />
    </div>
  );
}

export function App() {
  return (
    <Router>
      <AuthProvider>
        <MainAppContent />
      </AuthProvider>
    </Router>
  );
}

export default App;
