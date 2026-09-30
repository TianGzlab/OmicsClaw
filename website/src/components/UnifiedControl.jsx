import React from 'react';
import { motion } from 'framer-motion';
import { Terminal, Smartphone } from 'lucide-react';
import { useLang } from '../i18n/LanguageContext';

const UnifiedControl = () => {
  const { t } = useLang();

  return (
    <section className="py-24 relative" id="features">
      <div className="container mx-auto px-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="text-center mb-16"
        >
          <h2 className="text-3xl md:text-5xl font-bold mb-4">{t.unified.title1}<span className="text-gradient">{t.unified.titleHighlight}</span></h2>
          <p className="text-slate-400 max-w-2xl mx-auto text-lg">
            {t.unified.subtitle}
          </p>
        </motion.div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 items-center">
          {/* CLI Hub */}
          <motion.div
            initial={{ opacity: 0, x: -30 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            className="glass-card p-6 h-full flex flex-col"
          >
            <div className="flex items-center gap-3 mb-6">
              <Terminal className="text-teal-400 w-6 h-6" />
              <h3 className="text-xl font-semibold">{t.unified.cliTitle}</h3>
            </div>
            <div className="flex-1 bg-black/50 rounded-lg p-4 font-mono text-sm text-green-400 overflow-hidden border border-slate-800">
              <div className="flex gap-2 mb-4">
                <span className="w-3 h-3 rounded-full bg-red-500"></span>
                <span className="w-3 h-3 rounded-full bg-yellow-500"></span>
                <span className="w-3 h-3 rounded-full bg-green-500"></span>
              </div>
              <p className="opacity-70 mb-2">~ omicsclaw interactive</p>
              <p className="text-white mb-2">&gt; /research data.h5ad --idea "Find rare cell types"</p>
              <p className="opacity-70 mb-1">[Planner] Analyzing request...</p>
              <p className="mb-1">[Coder] Running spatial-cell-annotation</p>
              <p className="text-teal-400 mb-2">✔ Cell clusters identified with tangible markers.</p>
              <p className="opacity-70 motion-safe:animate-pulse">_</p>
            </div>
            <p className="mt-4 text-slate-400 text-sm">{t.unified.cliDesc}</p>
          </motion.div>

          {/* Mobile Hub */}
          <motion.div
            initial={{ opacity: 0, x: 30 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            className="glass-card p-6 h-full flex flex-col"
          >
            <div className="flex items-center gap-3 mb-6">
              <Smartphone className="text-cyan-400 w-6 h-6" />
              <h3 className="text-xl font-semibold">{t.unified.botTitle}</h3>
            </div>
            <div className="flex-1 rounded-xl p-4 bg-gradient-to-br from-slate-800 to-slate-900 border border-slate-700 flex flex-col gap-3 h-64 justify-end">
              <div className="self-end bg-teal-500/20 text-teal-100 p-3 rounded-2xl rounded-tr-sm text-sm border border-teal-500/30 max-w-[80%]">
                {t.unified.chatUser}
              </div>
              <div className="self-start bg-slate-800 text-slate-200 p-3 rounded-2xl rounded-tl-sm text-sm border border-slate-700 max-w-[80%]">
                <span className="block font-semibold mb-1 text-teal-400">🤖 OmicsBot</span>
                {t.unified.chatBot}
              </div>
            </div>
            <div className="mt-4 flex flex-wrap gap-2 text-xs text-slate-300">
              {['Telegram', 'Discord', 'Slack', 'Feishu', 'DingTalk', 'QQ', 'Email', 'iMessage'].map((p) => (
                <span key={p} className="bg-white/5 border border-white/10 py-1 px-3 rounded-full hover:bg-teal-500/10 hover:border-teal-500/30 transition-colors cursor-default">{p}</span>
              ))}
            </div>
          </motion.div>
        </div>
      </div>
    </section>
  );
};

export default UnifiedControl;
