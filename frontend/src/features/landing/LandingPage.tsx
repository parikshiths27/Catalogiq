import React from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, Sparkles, Sun, Moon } from 'lucide-react';
import { useTheme } from '../../hooks/useTheme';

export const LandingPage: React.FC = () => {
  const navigate = useNavigate();
  const { theme, toggleTheme } = useTheme();

  return (
    <div className="min-h-screen w-full bg-background text-foreground flex flex-col justify-between selection:bg-foreground selection:text-background relative overflow-hidden mesh-grid">
      
      {/* Background Ambient Glows */}
      <div className="absolute top-[-10%] right-[-10%] w-[50vw] h-[50vw] rounded-full glow-1 blur-[130px] pointer-events-none z-10" />
      <div className="absolute bottom-[-10%] left-[10%] w-[60vw] h-[60vw] rounded-full glow-2 blur-[160px] pointer-events-none z-10" />
      
      {/* Top Header */}
      <header className="w-full h-20 px-8 lg:px-12 flex items-center justify-between border-b border-border bg-background/80 backdrop-blur-xl z-30">
        <div className="flex items-center gap-3.5">
          <svg viewBox="0 0 100 100" className="w-6 h-6 text-foreground fill-current">
            <path d="M50 15 L85 85 L68 85 L50 45 L32 85 L15 85 Z" />
          </svg>
          <div>
            <span className="font-serif text-2xl font-medium tracking-normal text-foreground">CatalogIQ</span>
            <span className="hidden md:inline-block ml-3 text-[9px] font-light uppercase tracking-widest text-muted-foreground border-l border-border pl-3">
              Enterprise Catalog Intelligence
            </span>
          </div>
        </div>
        
        <nav className="flex items-center gap-6">
          <span 
            onClick={() => navigate('/upload')}
            className="hidden sm:inline-block text-[9px] uppercase tracking-widest text-muted-foreground hover:text-foreground cursor-pointer transition"
          >
            Ingestion
          </span>
          <span 
            onClick={() => navigate('/catalog')}
            className="hidden sm:inline-block text-[9px] uppercase tracking-widest text-muted-foreground hover:text-foreground cursor-pointer transition"
          >
            Reconciliation
          </span>
          <span 
            onClick={() => navigate('/reviews')}
            className="hidden sm:inline-block text-[9px] uppercase tracking-widest text-muted-foreground hover:text-foreground cursor-pointer transition"
          >
            Provenance
          </span>
          
          {/* Theme Toggle Button */}
          <button
            onClick={toggleTheme}
            className="w-9 h-9 border border-border bg-card text-muted-foreground hover:text-foreground hover:bg-accent transition flex items-center justify-center rounded-none"
            title={`Switch to ${theme === 'dark' ? 'Light' : 'Dark'} Mode`}
          >
            {theme === 'dark' ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
          </button>

          {/* Direct Launch Console Button */}
          <button
            onClick={() => navigate('/dashboard')}
            className="h-9 px-5 bg-foreground text-background hover:bg-transparent hover:text-foreground border border-foreground text-[9px] uppercase tracking-widest font-semibold transition duration-200 rounded-none flex items-center gap-2"
          >
            <span>Enter Console</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </nav>
      </header>

      {/* Main Body Grid */}
      <main className="flex-1 w-full px-8 lg:px-12 py-12 lg:py-16 grid grid-cols-1 lg:grid-cols-2 gap-12 items-center z-20">
        
        {/* Left column: Typography & Call to Actions */}
        <div className="space-y-8 max-w-xl">
          <div className="space-y-5">
            <div className="inline-flex items-center gap-2 border border-border bg-card/60 px-3 py-1.5 text-[9px] uppercase tracking-widest font-medium text-foreground">
              <Sparkles className="w-3.5 h-3.5 text-[#9B8F77]" />
              Multi-Source Ingestion & Entity Resolution
            </div>
            
            <h1 className="text-4xl sm:text-5xl lg:text-6xl font-normal leading-tight font-serif text-foreground tracking-normal">
              Unifying competing data without compromising truth.
            </h1>
            
            <p className="text-xs uppercase tracking-wider leading-relaxed text-muted-foreground font-light max-w-md">
              CatalogIQ ingests unstructured supplier documentation, resolving attributes, validating claims, and establishing clear source evidence provenance.
            </p>
          </div>

          {/* Action buttons */}
          <div className="flex flex-wrap items-center gap-4">
            <button
              onClick={() => navigate('/dashboard')}
              className="h-12 px-8 bg-foreground text-background border border-foreground hover:bg-transparent hover:text-foreground text-[10px] uppercase tracking-widest font-semibold transition duration-200 rounded-none flex items-center gap-2.5"
            >
              <span>Enter Dashboard</span>
              <ArrowRight className="w-4 h-4" />
            </button>
            <button
              onClick={() => navigate('/catalog')}
              className="h-12 px-8 bg-transparent text-muted-foreground hover:text-foreground border border-border hover:bg-card text-[10px] uppercase tracking-widest font-semibold transition duration-200 rounded-none flex items-center gap-2"
            >
              Explore Catalog
            </button>
          </div>

          {/* Minimal Key Indicators */}
          <div className="grid grid-cols-3 gap-6 pt-6 border-t border-border">
            <div className="space-y-1">
              <span className="text-[9px] text-muted-foreground uppercase tracking-widest block font-light">Stage 01</span>
              <span className="font-serif text-sm text-foreground font-medium block">Multi-Format Ingestion</span>
            </div>
            <div className="space-y-1">
              <span className="text-[9px] text-muted-foreground uppercase tracking-widest block font-light">Stage 02</span>
              <span className="font-serif text-sm text-foreground font-medium block">LLM Parsing & Specs</span>
            </div>
            <div className="space-y-1">
              <span className="text-[9px] text-muted-foreground uppercase tracking-widest block font-light">Stage 03</span>
              <span className="font-serif text-sm text-foreground font-medium block">Grounded Provenance</span>
            </div>
          </div>
        </div>

        {/* Right column: Identity visual with live capability card */}
        <div className="w-full flex items-center justify-center lg:justify-end">
          <div className="border border-border p-6 bg-card/85 backdrop-blur-md rounded-none max-w-md w-full relative z-20 space-y-6">
            <div className="aspect-square w-full overflow-hidden bg-background relative border border-border flex items-center justify-center">
              <img
                src="/brand_hero.png"
                alt="CatalogIQ Brand Symbol"
                className="w-full h-full object-cover"
                onError={(e) => {
                  // Fallback if image fails to load
                  (e.target as HTMLElement).style.display = 'none';
                }}
              />
            </div>

            <div className="space-y-3 pt-2">
              <div className="flex items-center justify-between text-xs">
                <span className="text-[10px] uppercase tracking-widest text-muted-foreground font-medium">Enterprise Pipeline</span>
                <span className="text-[10px] font-mono text-[#9B8F77] font-semibold">Active Telemetry</span>
              </div>
              <div className="grid grid-cols-2 gap-2 text-[11px]">
                <div className="p-2.5 border border-border bg-background/50 space-y-0.5">
                  <div className="text-[9px] uppercase tracking-widest text-muted-foreground">Supported Parsers</div>
                  <div className="font-mono font-medium text-foreground">PDF, XLSX, CSV, DOCX, ZIP</div>
                </div>
                <div className="p-2.5 border border-border bg-background/50 space-y-0.5">
                  <div className="text-[9px] uppercase tracking-widest text-muted-foreground">Vector Search</div>
                  <div className="font-mono font-medium text-foreground">Hybrid Vector + Lexical</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="w-full px-8 lg:px-12 py-6 border-t border-border flex flex-col sm:flex-row items-center justify-between gap-4 text-[10px] uppercase tracking-widest text-muted-foreground font-light z-20">
        <div>CatalogIQ Enterprise Data Engine — All systems operational</div>
        <div className="flex items-center gap-6">
          <span onClick={() => navigate('/search')} className="hover:text-foreground cursor-pointer transition">Search</span>
          <span onClick={() => navigate('/upload')} className="hover:text-foreground cursor-pointer transition">Batch Ingestion</span>
          <span onClick={() => navigate('/dashboard')} className="hover:text-foreground cursor-pointer transition">Console</span>
        </div>
      </footer>
    </div>
  );
};
