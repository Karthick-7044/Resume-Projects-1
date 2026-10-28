import { Link } from '@/lib/router';
import React from 'react';
import { Mail, Phone, ArrowUp } from 'lucide-react';

export function Footer() {
  const scrollToTop = () => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  return (
    <footer className="bg-void-950 text-slate-400 border-t border-white/10 py-16 relative overflow-hidden">
      <div className="max-w-7xl mx-auto px-6 sm:px-8 lg:px-12 space-y-12">
        
        {/* Main Footer Top Grid */}
        <div className="grid grid-cols-1 md:grid-cols-12 gap-8 items-start justify-between">
          
          {/* Brand & Description */}
          <div className="md:col-span-6 space-y-4">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-600 to-purple-600 flex items-center justify-center font-heading font-extrabold text-white text-base">
                α
              </div>
              <span className="font-heading font-bold text-lg text-white">
                Multi-Agent Alpha Discovery
              </span>
            </div>
            <p className="text-sm text-slate-400 leading-relaxed max-w-md">
              Multi-agent quantitative intelligence for regime-aware alpha factor discovery with transparent mathematical explanations.
            </p>
          </div>

          {/* Quick Navigation Links */}
          <div className="md:col-span-3 space-y-3">
            <div className="text-xs font-mono text-white uppercase tracking-wider font-semibold">
              Navigation
            </div>
            <ul className="space-y-2 text-sm">
              <li>
                <Link to="/company" className="hover:text-white transition-colors">Company</Link>
              </li>
              <li>
                <Link to="/services" className="hover:text-white transition-colors">Services</Link>
              </li>
              <li>
                <Link to="/contact" className="hover:text-white transition-colors">Contact Us</Link>
              </li>
            </ul>
          </div>

          {/* Direct Contact Details */}
          <div className="md:col-span-3 space-y-3">
            <div className="text-xs font-mono text-white uppercase tracking-wider font-semibold">
              Direct Contact
            </div>
            <ul className="space-y-2 text-sm">
              <li className="flex items-center gap-2">
                <Mail className="w-4 h-4 text-blue-400" />
                <a href="mailto:karthick704400@gmail.com" className="hover:text-white transition-colors font-mono text-xs">
                  karthick704400@gmail.com
                </a>
              </li>
              <li className="flex items-center gap-2">
                <Phone className="w-4 h-4 text-cyan-400" />
                <a href="tel:+917305125375" className="hover:text-white transition-colors font-mono text-xs">
                  Karthick: +91 7305125375
                </a>
              </li>
              <li className="flex items-center gap-2">
                <Phone className="w-4 h-4 text-purple-400" />
                <a href="tel:+919047402349" className="hover:text-white transition-colors font-mono text-xs">
                  Kavin Balaji: +91 9047402349
                </a>
              </li>
            </ul>
          </div>

        </div>

        {/* Footer Bottom Bar */}
        <div className="pt-8 border-t border-white/10 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs">
          <div className="text-slate-500">
            © 2026 Multi-Agent Alpha Discovery. All rights reserved.
          </div>
          
          <button
            onClick={scrollToTop}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-void-850 border border-white/10 text-slate-300 hover:text-white hover:border-blue-400/40 transition-all"
          >
            <span>Back to Top</span>
            <ArrowUp className="w-3.5 h-3.5" />
          </button>
        </div>

      </div>
    </footer>
  );
}
