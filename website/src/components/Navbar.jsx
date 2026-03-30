import React, { useState, useEffect } from 'react';
import { Menu, X, Dna, Languages } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import GithubIcon from './GithubIcon';
import { useLang } from '../i18n/LanguageContext';

const Navbar = () => {
  const [scrolled, setScrolled] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const { lang, toggleLang, t } = useLang();

  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 50);
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  const navLinks = [
    { name: t.nav.capabilities, href: '#features' },
    { name: t.nav.architecture, href: '#architecture' },
    { name: t.nav.memory, href: '#memory' },
    { name: t.nav.team, href: '#team' },
  ];

  return (
    <nav className={`fixed w-full z-50 transition-all duration-300 ${scrolled ? 'glass py-4' : 'bg-transparent py-6'}`}>
      <div className="container mx-auto px-6 flex items-center justify-between">
        <button 
          onClick={() => window.scrollTo(0, 0)}
          className="flex items-center gap-2 group hover:opacity-80 transition-opacity"
        >
          <Dna className="text-teal-400 w-8 h-8 group-hover:rotate-12 transition-transform duration-300" />
          <span className="text-xl font-bold tracking-tight text-white">Omics<span className="text-teal-400">Claw</span></span>
        </button>

        {/* Desktop Nav */}
        <div className="hidden md:flex items-center gap-8">
          <ul className="flex items-center gap-6">
            {navLinks.map((link) => (
              <li key={link.href}>
                <a href={link.href} className="text-sm text-slate-300 hover:text-teal-400 transition-colors">
                  {link.name}
                </a>
              </li>
            ))}
          </ul>

          {/* Language Toggle */}
          <button
            onClick={toggleLang}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-full glass hover:bg-white/10 transition-colors text-sm font-medium text-slate-300 hover:text-teal-400 group"
            title="Switch Language"
          >
            <Languages className="w-4 h-4 group-hover:-rotate-12 transition-transform duration-300" />
            <span>{lang === 'en' ? '中文' : 'EN'}</span>
          </button>

          <a
            href="https://github.com/TianGzlab/OmicsClaw"
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-2 px-4 py-2 rounded-full glass hover:bg-white/10 transition-colors border-teal-500/30 hover:border-teal-400 text-sm font-medium"
          >
            <GithubIcon className="w-4 h-4" />
            <span>{t.nav.github}</span>
          </a>
        </div>

        {/* Mobile Toggle */}
        <button className="md:hidden text-slate-300" onClick={() => setMobileOpen(!mobileOpen)}>
          {mobileOpen ? <X /> : <Menu />}
        </button>
      </div>

      {/* Mobile Menu */}
      <AnimatePresence>
        {mobileOpen && (
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="absolute top-full left-0 w-full glass border-none border-b border-white/10 py-4 px-6 md:hidden flex flex-col gap-4"
          >
            {navLinks.map((link) => (
              <a
                key={link.href}
                href={link.href}
                onClick={() => setMobileOpen(false)}
                className="text-slate-300 hover:text-teal-400"
              >
                {link.name}
              </a>
            ))}
            <button
              onClick={toggleLang}
              className="flex items-center gap-2 text-slate-300 hover:text-teal-400 mt-2"
            >
              <Languages className="w-5 h-5" />
              <span>{lang === 'en' ? '切换中文' : 'Switch to EN'}</span>
            </button>
            <a
              href="https://github.com/TianGzlab/OmicsClaw"
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-2 text-teal-400 mt-2"
            >
              <GithubIcon className="w-5 h-5" />
              <span>GitHub</span>
            </a>
          </motion.div>
        )}
      </AnimatePresence>
    </nav>
  );
};

export default Navbar;
