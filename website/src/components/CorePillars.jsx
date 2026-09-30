import React from 'react';
import { motion } from 'framer-motion';
import { Bot, MessageSquareText, Network } from 'lucide-react';
import { useLang } from '../i18n/LanguageContext';

const CorePillars = () => {
  const { t } = useLang();

  return (
    <section className="py-24 relative">
      <div className="container mx-auto px-6">
        <h2 className="text-3xl md:text-5xl font-bold mb-16 text-center">{t.pillars.title1}<span className="text-gradient">{t.pillars.titleHighlight}</span></h2>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Pillar 1: Large card spanning 2 columns on desktop */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            whileInView={{ opacity: 1, scale: 1 }}
            viewport={{ once: true }}
            className="md:col-span-2 glass-card p-8 flex flex-col justify-between group relative"
          >
            <div className="absolute top-0 right-0 p-8 opacity-10 group-hover:opacity-20 transition-opacity">
               <Bot className="w-48 h-48 text-teal-400" />
            </div>
            <div className="relative z-10">
              <h3 className="text-2xl font-bold mb-2">{t.pillars.p1Title}</h3>
              <p className="text-slate-400 mb-6 max-w-xl">{t.pillars.p1Desc}</p>
            </div>
            
            <div className="relative z-10 bg-black/80 rounded-lg p-5 font-mono text-xs sm:text-sm border border-slate-700 max-w-xl">
              <p className="text-cyan-400 mb-1"># Mode A: PDF + idea</p>
              <p className="mb-3 text-slate-300 break-all">/research paper.pdf --idea "explore TME heterogeneity"</p>
              <p className="text-teal-400 mb-1"># Mode B: PDF + idea + data</p>
              <p className="mb-3 text-slate-300 break-all">/research paper.pdf --idea "..." --h5ad data.h5ad</p>
              <p className="text-emerald-400 mb-1"># Mode C: Idea only</p>
              <p className="text-slate-300 break-all">/research --idea "explore TME heterogeneity"</p>
            </div>
          </motion.div>

          {/* Pillar 2: Conversational Interface */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="glass-card p-6 group relative overflow-hidden flex flex-col gap-4"
          >
            <h3 className="text-2xl font-bold">{t.pillars.p2Title}</h3>
            <p className="text-slate-400 text-sm leading-relaxed">
              {t.pillars.p2Desc}
            </p>
            {/* Feature highlights */}
            <ul className="text-xs text-slate-300 space-y-2">
              <li className="flex items-center gap-2"><span className="w-1.5 h-1.5 rounded-full bg-teal-400 shrink-0" />Natural language → analysis pipeline</li>
              <li className="flex items-center gap-2"><span className="w-1.5 h-1.5 rounded-full bg-cyan-400 shrink-0" />CLI / TUI / Feishu / Telegram / 9+ channels</li>
              <li className="flex items-center gap-2"><span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shrink-0" />Session resume & slash commands</li>
            </ul>
            {/* Schematic: multi-surface chat diagram */}
            <div className="flex-1 grid grid-cols-2 gap-2 min-h-0">
              {/* CLI mini mockup */}
              <div className="rounded-lg border border-slate-700 bg-black/60 p-3 text-[10px] font-mono">
                <div className="flex gap-1 mb-2">
                  <span className="w-2 h-2 rounded-full bg-red-500/70" />
                  <span className="w-2 h-2 rounded-full bg-yellow-500/70" />
                  <span className="w-2 h-2 rounded-full bg-green-500/70" />
                </div>
                <div className="space-y-1">
                  <p className="text-slate-500">$ oc interactive</p>
                  <p className="text-cyan-400">🧬 OmicsClaw v0.3.0</p>
                  <p className="text-slate-600">Type /help for commands</p>
                  <p className="text-white mt-1">→ run spatial QC on my Visium data</p>
                  <p className="text-slate-400">[Router] Matched: spatial-qc</p>
                  <p className="text-slate-400">[Skill] Loading data.h5ad...</p>
                  <p className="text-teal-400">✔ QC complete. 3 plots saved.</p>
                  <p className="text-white mt-1">→ find spatial domains</p>
                  <p className="text-slate-400">[Router] Matched: spatial-domains</p>
                  <p className="text-teal-400">✔ 5 domains identified.</p>
                  <p className="text-slate-600 animate-pulse">_</p>
                </div>
              </div>
              {/* Bot chat mini mockup */}
              <div className="rounded-lg border border-slate-700 bg-slate-900/80 p-3 text-[10px] space-y-1.5 flex flex-col justify-end">
                <div className="self-end bg-teal-500/20 text-teal-200 px-2 py-1 rounded-lg rounded-tr-sm border border-teal-500/20 max-w-[90%]">
                  Hi, annotate cell types for me
                </div>
                <div className="self-start bg-slate-800 text-slate-300 px-2 py-1 rounded-lg rounded-tl-sm border border-slate-700 max-w-[90%]">
                  <span className="text-teal-400 font-bold">🤖</span> Running sc-annotate...
                </div>
                <div className="self-start bg-slate-800 text-slate-300 px-2 py-1 rounded-lg rounded-tl-sm border border-slate-700 max-w-[90%]">
                  <span className="text-teal-400 font-bold">🤖</span> Found 8 cell types. Report saved ✔
                </div>
                <div className="self-end bg-teal-500/20 text-teal-200 px-2 py-1 rounded-lg rounded-tr-sm border border-teal-500/20 max-w-[90%]">
                  Show pathway enrichment
                </div>
                <div className="self-start bg-slate-800 text-slate-300 px-2 py-1 rounded-lg rounded-tl-sm border border-slate-700 max-w-[90%]">
                  <span className="text-teal-400 font-bold">🤖</span> Top 3: TNF-α, IL-6, NF-κB
                </div>
                <div className="flex gap-1 mt-1">
                  <span className="text-[8px] bg-white/5 border border-white/10 px-1.5 py-0.5 rounded-full text-slate-400">Feishu</span>
                  <span className="text-[8px] bg-white/5 border border-white/10 px-1.5 py-0.5 rounded-full text-slate-400">Telegram</span>
                </div>
              </div>
            </div>
          </motion.div>

          {/* Pillar 3: Persistent Memory */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: 0.1 }}
            className="glass-card p-6 group relative overflow-hidden flex flex-col gap-4 bg-gradient-to-br hover:from-slate-900 hover:to-teal-900/20 transition-colors duration-500"
          >
            <h3 className="text-2xl font-bold">{t.pillars.p3Title}</h3>
            <p className="text-slate-400 text-sm leading-relaxed">
              {t.pillars.p3Desc}
            </p>
            {/* Feature highlights */}
            <ul className="text-xs text-slate-300 space-y-2">
              <li className="flex items-center gap-2"><span className="w-1.5 h-1.5 rounded-full bg-teal-400 shrink-0" />Datasets & analysis lineage auto-tracked</li>
              <li className="flex items-center gap-2"><span className="w-1.5 h-1.5 rounded-full bg-purple-400 shrink-0" />User preferences persisted cross-session</li>
              <li className="flex items-center gap-2"><span className="w-1.5 h-1.5 rounded-full bg-amber-400 shrink-0" />Visual Memory Explorer dashboard</li>
            </ul>
            {/* Schematic: graph memory network */}
            <div className="flex-1 rounded-lg border border-slate-700 bg-black/40 p-3 group-hover:border-teal-500/30 transition-colors flex items-center">
              <svg viewBox="0 0 280 120" className="w-full h-auto" fill="none">
                {/* Edges */}
                <line x1="140" y1="30" x2="60" y2="70" stroke="#0d9488" strokeWidth="1.5" opacity="0.4" />
                <line x1="140" y1="30" x2="220" y2="70" stroke="#0d9488" strokeWidth="1.5" opacity="0.4" />
                <line x1="140" y1="30" x2="140" y2="95" stroke="#0d9488" strokeWidth="1.5" opacity="0.4" />
                <line x1="60" y1="70" x2="140" y2="95" stroke="#0d9488" strokeWidth="1" opacity="0.25" />
                <line x1="220" y1="70" x2="140" y2="95" stroke="#0d9488" strokeWidth="1" opacity="0.25" />
                <line x1="60" y1="70" x2="20" y2="100" stroke="#0d9488" strokeWidth="1" opacity="0.2" />
                <line x1="220" y1="70" x2="260" y2="100" stroke="#0d9488" strokeWidth="1" opacity="0.2" />
                {/* Root node */}
                <circle cx="140" cy="30" r="12" fill="#0d9488" opacity="0.3" />
                <circle cx="140" cy="30" r="7" fill="#14b8a6" className="animate-pulse" />
                <text x="140" y="13" textAnchor="middle" fill="#5eead4" fontSize="8" fontFamily="monospace">ROOT</text>
                {/* Session node */}
                <circle cx="60" cy="70" r="9" fill="#0ea5e9" opacity="0.3" />
                <circle cx="60" cy="70" r="5" fill="#22d3ee" />
                <text x="60" y="58" textAnchor="middle" fill="#67e8f9" fontSize="7" fontFamily="monospace">Session</text>
                {/* Dataset node */}
                <circle cx="220" cy="70" r="9" fill="#8b5cf6" opacity="0.3" />
                <circle cx="220" cy="70" r="5" fill="#a78bfa" />
                <text x="220" y="58" textAnchor="middle" fill="#c4b5fd" fontSize="7" fontFamily="monospace">Dataset</text>
                {/* Preference node */}
                <circle cx="140" cy="95" r="9" fill="#f59e0b" opacity="0.3" />
                <circle cx="140" cy="95" r="5" fill="#fbbf24" />
                <text x="140" y="115" textAnchor="middle" fill="#fcd34d" fontSize="7" fontFamily="monospace">Preference</text>
                {/* Leaf nodes */}
                <circle cx="20" cy="100" r="4" fill="#22d3ee" opacity="0.4" />
                <circle cx="260" cy="100" r="4" fill="#a78bfa" opacity="0.4" />
              </svg>
            </div>
          </motion.div>
        </div>
      </div>
    </section>
  );
};

export default CorePillars;
