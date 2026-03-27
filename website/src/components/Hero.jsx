import React from 'react';
import { motion } from 'framer-motion';
import { Terminal, BookOpen, ArrowRight } from 'lucide-react';
import { useLang } from '../i18n/LanguageContext';

const Hero = () => {
  const { t } = useLang();

  return (
    <section className="relative min-h-screen flex items-center justify-center pt-20 overflow-hidden">
      {/* Background glow effects */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[800px] bg-teal-500/10 rounded-full blur-[120px] opacity-50 animate-pulse mix-blend-screen pointer-events-none" />
      <div className="absolute top-1/4 right-1/4 w-[400px] h-[400px] bg-cyan-500/10 rounded-full blur-[100px] opacity-40 pointer-events-none" />

      <div className="container mx-auto px-6 text-center z-10">
        
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5 }}
          className="inline-flex items-center gap-2 px-3 py-1 rounded-full glass mb-8"
        >
          <span className="flex h-2 w-2 rounded-full bg-teal-400 animate-pulse" />
          <span className="text-xs font-medium text-slate-300">{t.hero.badge}</span>
        </motion.div>

        <motion.h1 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.1 }}
          className="text-5xl md:text-7xl font-bold tracking-tight mb-6"
        >
          {t.hero.title1} <br className="hidden md:block" />
          {t.hero.title2}<span className="text-gradient">{t.hero.titleHighlight}</span>
        </motion.h1>

        <motion.p 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.2 }}
          className="text-lg md:text-xl text-slate-400 max-w-3xl mx-auto mb-10 leading-relaxed"
        >
          {t.hero.subtitle}
        </motion.p>

        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.3 }}
          className="flex flex-col sm:flex-row items-center justify-center gap-4"
        >
          <a href="#features" className="group flex items-center gap-2 px-8 py-4 bg-gradient-to-r from-teal-500 to-cyan-600 hover:from-teal-400 hover:to-cyan-500 text-white rounded-full font-medium transition-all shadow-lg shadow-teal-500/25">
             {t.hero.cta1}
             <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
          </a>
          <a href="https://github.com/TianGzlab/OmicsClaw" target="_blank" rel="noreferrer" className="flex items-center gap-2 px-8 py-4 glass hover:bg-white/10 rounded-full font-medium text-slate-200 transition-all">
             <Terminal className="w-5 h-5" />
             {t.hero.cta2}
          </a>
          <a href="https://github.com/TianGzlab/OmicsClaw" target="_blank" rel="noreferrer" className="flex items-center gap-2 px-8 py-4 text-slate-400 hover:text-white transition-colors">
            <BookOpen className="w-5 h-5" />
            {t.hero.cta3}
          </a>
        </motion.div>

      </div>
    </section>
  );
};

export default Hero;
