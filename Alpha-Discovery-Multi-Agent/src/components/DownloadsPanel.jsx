import React, { useEffect, useState } from 'react';
import { Download, FileText } from 'lucide-react';
import { fetchDownloads, fileUrl } from '@/lib/api';

const LABELS = {
  'paper_v3.docx': ['Journal paper (IEEE format, v3)', 'Full paper with results, robustness study and demo figures'],
  'results_v3.md': ['Results table', 'What is and is not significant, with corrected p-values'],
  'project_report_simple.md': ['Plain-English report', 'Everything we built and found, in simple words'],
  'framework_guide.md': ['Framework guide + file map', 'How every module works and where every file is'],
};

export function DownloadsPanel() {
  const [files, setFiles] = useState([]);
  useEffect(() => { fetchDownloads().then(setFiles).catch(() => setFiles([])); }, []);
  return (
    <div className="glass-card rounded-3xl p-6 border border-white/15 space-y-4">
      <h3 className="font-heading text-xl font-bold text-white flex items-center gap-2"><FileText className="w-5 h-5 text-cyan-400" />Paper &amp; downloads</h3>
      <div className="grid md:grid-cols-2 gap-3">
        {files.map((f) => {
          const [title, desc] = LABELS[f.name] || [f.name, f.path];
          return (
            <a key={f.name} href={f.exists ? fileUrl(f.name) : undefined}
              className={`rounded-2xl border p-4 flex items-start gap-3 ${f.exists ? 'border-white/10 bg-black/30 hover:border-cyan-500/50' : 'border-white/5 bg-black/10 opacity-50 pointer-events-none'}`}>
              <Download className="w-5 h-5 text-cyan-400 shrink-0 mt-0.5" />
              <div><div className="text-sm text-white font-semibold">{title}</div><div className="text-xs text-slate-400">{desc}</div>
                <div className="text-[10px] font-mono text-slate-500 mt-1">{f.path}</div></div>
            </a>
          );
        })}
      </div>
    </div>
  );
}
