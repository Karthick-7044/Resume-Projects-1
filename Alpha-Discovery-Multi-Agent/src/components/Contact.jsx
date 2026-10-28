import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { Mail, Phone, Building2, ArrowUpRight, Send, CheckCircle2, User, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';

export function Contact() {
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    company: '',
    interest: 'Multi-Agent Alpha Discovery',
    message: '',
  });

  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);

  const TO = 'karthick704400@gmail.com';

  const buildMailto = () => {
    const subject = `Research enquiry: ${formData.interest}`;
    const body = [
      `Name: ${formData.name}`,
      `Email: ${formData.email}`,
      `Organisation: ${formData.company || '-'}`,
      `Research focus: ${formData.interest}`,
      '',
      formData.message,
    ].join('\n');
    return `mailto:${TO}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
  };

  // No server is needed: the message is composed in the visitor's own mail app and sent from their address.
  const handleSubmit = (e) => {
    e.preventDefault();
    setLoading(true);
    window.location.href = buildMailto();
    setTimeout(() => {
      setLoading(false);
      setSubmitted(true);
    }, 600);
  };

  return (
    <section id="contact" className="relative py-28 bg-[#050505] text-slate-100 overflow-hidden">
      {/* Background Glows */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-blue-600/10 rounded-full blur-[160px] pointer-events-none" />
      <div className="absolute inset-0 bg-grid-pattern opacity-30 pointer-events-none" />

      <div className="relative max-w-7xl mx-auto px-6 sm:px-8 lg:px-12">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-start">
          
          {/* Contact Information Column */}
          <div className="lg:col-span-5 space-y-8">
            <div className="space-y-4">
              <div className="inline-flex items-center gap-2 px-3.5 py-1 rounded-full bg-blue-950/40 border border-blue-500/30 text-xs font-mono text-cyan-300">
                <Sparkles className="w-3.5 h-3.5 text-cyan-400" />
                <span>DIRECT RESEARCH ENGAGEMENT</span>
              </div>

              <h2 className="font-heading text-3xl sm:text-5xl font-extrabold tracking-tight text-white">
                Let's Discover <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-400 via-indigo-300 to-purple-400">What's Next.</span>
              </h2>

              <p className="text-slate-300 text-base sm:text-lg leading-relaxed">
                Have a research problem, quantitative strategy, or alpha discovery challenge? Let's build the research system around it.
              </p>
            </div>

            {/* Direct Contact Cards */}
            <div className="space-y-4 pt-2">
              <div className="text-xs font-mono text-cyan-400 font-semibold tracking-wider uppercase mb-2">
                RESEARCH LEADERSHIP & DIRECT LINES
              </div>

              {/* Team Member 1: Karthick */}
              <div className="glass-card rounded-2xl p-5 border border-white/10 space-y-3 hover:border-blue-500/40 transition-all">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-blue-600/20 border border-blue-500/30 flex items-center justify-center text-cyan-400 font-bold text-base">
                    <User className="w-5 h-5" />
                  </div>
                  <div>
                    <div className="font-heading font-bold text-lg text-white">Karthick</div>
                    <div className="text-xs font-mono text-blue-400">Research Director & Quant Lead</div>
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1 border-t border-white/5 text-xs font-mono">
                  <a
                    href="mailto:karthick704400@gmail.com"
                    className="flex items-center gap-2 p-2 rounded-lg bg-black/40 text-slate-300 hover:text-white hover:bg-white/5 transition-colors truncate"
                  >
                    <Mail className="w-3.5 h-3.5 text-purple-400 shrink-0" />
                    <span className="truncate">karthick704400@gmail.com</span>
                  </a>
                  <a
                    href="tel:+917305125375"
                    className="flex items-center gap-2 p-2 rounded-lg bg-black/40 text-slate-300 hover:text-white hover:bg-white/5 transition-colors"
                  >
                    <Phone className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
                    <span>+91 7305125375</span>
                  </a>
                </div>
              </div>

              {/* Team Member 2: Kavin Balaji */}
              <div className="glass-card rounded-2xl p-5 border border-white/10 space-y-3 hover:border-purple-500/40 transition-all">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-purple-600/20 border border-purple-500/30 flex items-center justify-center text-purple-400 font-bold text-base">
                    <User className="w-5 h-5" />
                  </div>
                  <div>
                    <div className="font-heading font-bold text-lg text-white">Kavin Balaji</div>
                    <div className="text-xs font-mono text-purple-400">Research Partner & AI Architect</div>
                  </div>
                </div>

                <div className="pt-1 border-t border-white/5 text-xs font-mono">
                  <a
                    href="tel:+919047402349"
                    className="flex items-center justify-between p-2.5 rounded-lg bg-black/40 text-slate-300 hover:text-white hover:bg-white/5 transition-colors group"
                  >
                    <div className="flex items-center gap-2">
                      <Phone className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
                      <span className="font-semibold text-white group-hover:text-cyan-300">+91 9047402349</span>
                    </div>
                    <ArrowUpRight className="w-4 h-4 text-slate-400 group-hover:text-white group-hover:translate-x-0.5 transition-transform" />
                  </a>
                </div>
              </div>

            </div>
          </div>

          {/* Contact Form Column */}
          <div className="lg:col-span-7">
            <div className="glass-card rounded-3xl p-8 sm:p-10 border border-white/15 shadow-2xl relative">
              
              {submitted ? (
                <motion.div
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  className="text-center py-12 space-y-4"
                >
                  <div className="w-16 h-16 rounded-full bg-emerald-500/20 border border-emerald-500/40 text-emerald-400 flex items-center justify-center mx-auto">
                    <CheckCircle2 className="w-8 h-8" />
                  </div>
                  <h3 className="font-heading text-2xl font-bold text-white">
                    Your email is ready to send
                  </h3>
                  <p className="text-slate-300 text-sm max-w-md mx-auto">
                    Thank you, {formData.name}. Your mail app should have opened with the message filled in. Press Send there to deliver it to Karthick and the research team. If nothing opened, write to {TO} directly.
                  </p>
                  <Button
                    variant="outline"
                    onClick={() => {
                      setSubmitted(false);
                      setFormData({ name: '', email: '', company: '', interest: 'Multi-Agent Alpha Discovery', message: '' });
                    }}
                    className="mt-4"
                  >
                    Send Another Message
                  </Button>
                </motion.div>
              ) : (
                <form onSubmit={handleSubmit} className="space-y-5">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
                    {/* Name */}
                    <div className="space-y-2">
                      <label className="text-xs font-mono text-slate-300 uppercase tracking-wider">
                        Your Name *
                      </label>
                      <Input
                        required
                        type="text"
                        placeholder="Dr. Alexander Vance"
                        value={formData.name}
                        onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                      />
                    </div>

                    {/* Email */}
                    <div className="space-y-2">
                      <label className="text-xs font-mono text-slate-300 uppercase tracking-wider">
                        Work Email *
                      </label>
                      <Input
                        required
                        type="email"
                        placeholder="a.vance@fund.com"
                        value={formData.email}
                        onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
                    {/* Company */}
                    <div className="space-y-2">
                      <label className="text-xs font-mono text-slate-300 uppercase tracking-wider">
                        Institution / Organization
                      </label>
                      <Input
                        type="text"
                        placeholder="Vance Quantitative Capital"
                        value={formData.company}
                        onChange={(e) => setFormData({ ...formData, company: e.target.value })}
                      />
                    </div>

                    {/* Research Interest */}
                    <div className="space-y-2">
                      <label className="text-xs font-mono text-slate-300 uppercase tracking-wider">
                        Research Focus
                      </label>
                      <select
                        className="flex h-11 w-full rounded-xl bg-white/[0.06] px-4 py-2 text-sm text-slate-100 shadow-inner backdrop-blur-md transition-all focus:border-blue-500/60 focus:bg-[#0f0f14] focus:outline-none"
                        value={formData.interest}
                        onChange={(e) => setFormData({ ...formData, interest: e.target.value })}
                      >
                        <option value="Multi-Agent Alpha Discovery">Multi-Agent Alpha Discovery</option>
                        <option value="Regime-Aware Factor Research">Regime-Aware Factor Research</option>
                        <option value="Explainable Factor Intelligence">Explainable Factor Intelligence</option>
                        <option value="Factor Validation & Robustness">Factor Validation & Robustness</option>
                        <option value="Market Microstructure Intelligence">Market Microstructure Intelligence</option>
                        <option value="Research Intelligence Infrastructure">Custom Infrastructure Build</option>
                      </select>
                    </div>
                  </div>

                  {/* Message */}
                  <div className="space-y-2">
                    <label className="text-xs font-mono text-slate-300 uppercase tracking-wider">
                      Research Parameters & Requirements *
                    </label>
                    <Textarea
                      required
                      placeholder="Specify asset classes, target holding horizons, or factor research objectives..."
                      value={formData.message}
                      onChange={(e) => setFormData({ ...formData, message: e.target.value })}
                    />
                  </div>

                  {/* Submit Button */}
                  <Button
                    type="submit"
                    disabled={loading}
                    variant="default"
                    size="lg"
                    className="w-full text-base font-semibold"
                  >
                    {loading ? (
                      <span className="flex items-center gap-2">
                        <span className="w-4 h-4 rounded-full border-2 border-white border-t-transparent animate-spin" />
                        Opening your mail app...
                      </span>
                    ) : (
                      <span className="flex items-center gap-2">
                        <span>Start a Conversation</span>
                        <Send className="w-4 h-4 ml-1" />
                      </span>
                    )}
                  </Button>
                </form>
              )}

            </div>
          </div>

        </div>
      </div>
    </section>
  );
}
