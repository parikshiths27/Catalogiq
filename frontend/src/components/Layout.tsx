import React from 'react';
import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { CatalogIQAssistant } from './assistant/CatalogIQAssistant';

export const Layout: React.FC = () => {
  return (
    <div className="flex h-screen w-screen overflow-hidden bg-background text-foreground relative">
      <Sidebar />
      <main className="flex-1 flex flex-col min-w-0 overflow-y-auto">
        <header className="h-16 border-b px-8 flex items-center justify-between shrink-0 bg-card">
          <div className="flex items-center gap-4">
            <span className="text-xs px-2.5 py-1 rounded bg-secondary font-mono text-muted-foreground border">
              v1.0.0-beta
            </span>
          </div>
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-secondary flex items-center justify-center border font-semibold text-sm">
              M
            </div>
            <span className="text-sm font-medium text-muted-foreground">Catalog Manager</span>
          </div>
        </header>
        <div className="flex-1 p-8">
          <Outlet />
        </div>
      </main>
      <CatalogIQAssistant />
    </div>
  );
};

