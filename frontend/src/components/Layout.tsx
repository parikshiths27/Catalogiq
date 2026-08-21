import React, { useState, useEffect } from 'react';
import { Outlet, useNavigate } from 'react-router-dom';
import { Command, Search, Sun, Moon, Maximize, Minimize } from 'lucide-react';
import { Sidebar } from './Sidebar';
import { useTheme } from '../hooks/useTheme';
import { CatalogIQAssistant } from './assistant/CatalogIQAssistant';

export const Layout: React.FC = () => {
  const navigate = useNavigate();
  const { theme, toggleTheme } = useTheme();
  const [isFullscreen, setIsFullscreen] = useState(false);

  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(!!document.fullscreenElement);
    };
    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', handleFullscreenChange);
  }, []);

  const toggleFullscreen = () => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen().catch((err) => {
        console.error("Error enabling full-screen mode:", err);
      });
    } else {
      if (document.exitFullscreen) {
        document.exitFullscreen();
      }
    }
  };

  return (
    <div className="app-chrome mesh-grid flex h-screen w-screen overflow-hidden bg-background text-foreground rounded-none relative">
      
      {/* Background Ambient Glows */}
      <div className="absolute top-[-10%] right-[-10%] w-[45vw] h-[45vw] rounded-full glow-1 blur-[130px] pointer-events-none z-0" />
      <div className="absolute bottom-[-10%] left-[20%] w-[55vw] h-[55vw] rounded-full glow-2 blur-[160px] pointer-events-none z-0" />

      <Sidebar />
      
      <main className="flex-1 flex flex-col min-w-0 overflow-y-auto z-10 bg-transparent relative w-full h-full">
        <header className="h-16 border-b border-border px-8 flex items-center justify-between shrink-0 bg-background/80 backdrop-blur-md sticky top-0 z-30">
          <div className="flex items-center gap-3 min-w-0">
            <div 
              onClick={() => navigate('/search')}
              className="hidden md:flex items-center gap-2 h-9 w-[360px] rounded-none border border-border bg-card px-3 text-muted-foreground cursor-pointer hover:border-foreground/40 transition"
            >
              <Search className="w-4 h-4 text-foreground" />
              <span className="text-xs font-light tracking-wide truncate">Search products, SKUs, attributes...</span>
              <span className="ml-auto inline-flex items-center gap-1 rounded-none border border-border bg-background px-1.5 py-0.5 text-[9px] font-mono text-muted-foreground">
                <Command className="w-2.5 h-2.5" /> K
              </span>
            </div>
            <span className="text-[10px] uppercase tracking-widest px-2.5 py-1 rounded-none bg-[#9B8F77]/10 font-mono text-[#9B8F77] border border-[#9B8F77]/20">
              Live Console
            </span>
          </div>
          <div className="flex items-center gap-3">
            {/* Fullscreen Toggle Button */}
            <button 
              onClick={toggleFullscreen}
              className="w-9 h-9 rounded-none border border-border bg-card text-muted-foreground hover:text-foreground hover:bg-accent transition flex items-center justify-center"
              title={isFullscreen ? "Exit Fullscreen Mode" : "Enter Fullscreen Mode"}
            >
              {isFullscreen ? <Minimize className="w-4 h-4" /> : <Maximize className="w-4 h-4" />}
            </button>

            {/* Theme Toggle Button */}
            <button 
              onClick={toggleTheme}
              className="w-9 h-9 rounded-none border border-border bg-card text-muted-foreground hover:text-foreground hover:bg-accent transition flex items-center justify-center"
              title={`Switch to ${theme === 'dark' ? 'Light' : 'Dark'} Mode`}
            >
              {theme === 'dark' ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
            </button>
            
            <div className="w-9 h-9 rounded-none border border-foreground bg-card flex items-center justify-center font-mono text-foreground text-xs font-medium">
              CQ
            </div>
          </div>
        </header>
        <div className="flex-1 p-6 lg:p-8 overflow-y-auto bg-transparent w-full h-full max-w-full">
          <Outlet />
        </div>
      </main>

      <CatalogIQAssistant />
    </div>
  );
};
