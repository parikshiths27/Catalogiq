import React from 'react';
import { LucideIcon } from 'lucide-react';

interface StatCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: LucideIcon;
  trend?: {
    value: string;
    isPositive?: boolean;
  };
  accentColor?: 'indigo' | 'amber' | 'emerald' | 'rose' | 'sky';
  className?: string;
}

export const StatCard: React.FC<StatCardProps> = ({
  title,
  value,
  subtitle,
  icon: Icon,
  trend,
  accentColor = 'indigo',
  className = '',
}) => {
  const accentStyles = {
    indigo: {
      border: 'hover:border-indigo-500/40',
      iconBg: 'bg-indigo-500/10 text-indigo-400 border-indigo-500/20',
      glow: 'group-hover:shadow-[0_0_20px_-5px_rgba(99,102,241,0.2)]',
    },
    amber: {
      border: 'hover:border-amber-500/40',
      iconBg: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
      glow: 'group-hover:shadow-[0_0_20px_-5px_rgba(245,158,11,0.2)]',
    },
    emerald: {
      border: 'hover:border-emerald-500/40',
      iconBg: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
      glow: 'group-hover:shadow-[0_0_20px_-5px_rgba(16,185,129,0.2)]',
    },
    rose: {
      border: 'hover:border-rose-500/40',
      iconBg: 'bg-rose-500/10 text-rose-400 border-rose-500/20',
      glow: 'group-hover:shadow-[0_0_20px_-5px_rgba(244,63,94,0.2)]',
    },
    sky: {
      border: 'hover:border-sky-500/40',
      iconBg: 'bg-sky-500/10 text-sky-400 border-sky-500/20',
      glow: 'group-hover:shadow-[0_0_20px_-5px_rgba(14,165,233,0.2)]',
    },
  }[accentColor];

  return (
    <div
      className={`group glass-card p-5 rounded-xl border border-slate-800/80 transition-all duration-300 ${accentStyles.border} ${accentStyles.glow} ${className}`}
    >
      <div className="flex items-start justify-between">
        <div className="space-y-1.5">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
            {title}
          </span>
          <div className="text-2xl lg:text-3xl font-extrabold tracking-tight text-white font-mono">
            {value}
          </div>
          {subtitle && (
            <p className="text-xs text-slate-400 font-medium">{subtitle}</p>
          )}
        </div>
        <div className={`p-2.5 rounded-lg border ${accentStyles.iconBg}`}>
          <Icon className="w-5 h-5" />
        </div>
      </div>
      {trend && (
        <div className="mt-3 pt-3 border-t border-slate-800/60 flex items-center gap-2 text-xs">
          <span
            className={`font-semibold ${
              trend.isPositive ? 'text-emerald-400' : 'text-slate-400'
            }`}
          >
            {trend.value}
          </span>
        </div>
      )}
    </div>
  );
};
