import React from 'react';
import { NavLink, Link } from 'react-router-dom';
import {
  LayoutDashboard,
  Database,
  UploadCloud,
  Search,
  CheckSquare,
  Home,
  FileText,
  HeartPulse
} from 'lucide-react';

interface SidebarItemProps {
  to: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}

const SidebarItem: React.FC<SidebarItemProps> = ({ to, label, icon: Icon }) => {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `group flex items-center gap-3 px-4 py-3 text-xs uppercase tracking-widest font-light transition-all duration-150 rounded-none ${
          isActive
            ? 'bg-accent text-foreground border-l-2 border-foreground font-medium'
            : 'text-muted-foreground hover:bg-card hover:text-foreground'
        }`
      }
    >
      <Icon className="w-4 h-4 shrink-0 opacity-80 group-hover:opacity-100 transition-opacity" />
      <span>{label}</span>
    </NavLink>
  );
};

export const Sidebar: React.FC = () => {
  return (
    <aside className="w-72 border-r border-border bg-background flex flex-col h-screen select-none rounded-none transition-colors duration-200 shrink-0">
      {/* Brand Header */}
      <Link 
        to="/" 
        className="p-6 border-b border-border flex items-center gap-3.5 hover:bg-accent/40 transition cursor-pointer select-none"
      >
        <svg viewBox="0 0 100 100" className="w-6 h-6 text-foreground fill-current">
          <path d="M50 15 L85 85 L68 85 L50 45 L32 85 L15 85 Z" />
        </svg>
        <div>
          <h1 className="font-medium text-2xl tracking-normal text-foreground font-serif">CatalogIQ</h1>
          <span className="text-[9px] font-light uppercase tracking-widest text-muted-foreground">
            Product Intelligence
          </span>
        </div>
      </Link>

      {/* AI Layer Alert Panel (Boxy & Minimalist) */}
      <div className="mx-4 mt-5 border border-border bg-card p-4 rounded-none">
        <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-foreground">
          <span className="w-1.5 h-1.5 bg-[#9B8F77]"></span>
          AI Core System
        </div>
        <p className="mt-2.5 text-[11px] leading-relaxed text-muted-foreground font-light">
          Confidence scoring, entity reconciliation, and verification grounding.
        </p>
      </div>

      {/* Navigation */}
      <nav className="flex-1 mt-6 space-y-0.5 overflow-y-auto">
        <SidebarItem to="/dashboard" label="Overview" icon={LayoutDashboard} />
        <SidebarItem to="/catalog" label="Catalog" icon={Database} />
        <SidebarItem to="/upload" label="Upload & Batch" icon={UploadCloud} />
        <SidebarItem to="/jobs" label="Processing" icon={FileText} />
        <SidebarItem to="/search" label="Hybrid Search" icon={Search} />
        <SidebarItem to="/reviews" label="Reviews & Triage" icon={CheckSquare} />
        <SidebarItem to="/health" label="System Health" icon={HeartPulse} />
      </nav>

      {/* Status Bar */}
      <div className="mx-4 mb-4 border border-border bg-card p-3 rounded-none">
        <div className="flex items-center justify-between text-[9px] font-medium uppercase tracking-widest text-muted-foreground">
          <span>Processing Pipeline</span>
          <span className="text-[#9B8F77]">Active</span>
        </div>
        <div className="mt-2.5 h-[2px] w-full bg-border rounded-none">
          <div className="h-full w-full bg-foreground rounded-none" />
        </div>
      </div>

      <div className="border-t border-border flex flex-col">
        <SidebarItem to="/" label="Exit to Landing" icon={Home} />
      </div>
    </aside>
  );
};
