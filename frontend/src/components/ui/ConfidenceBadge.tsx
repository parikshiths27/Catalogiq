import React from 'react';

interface ConfidenceBadgeProps {
  confidence: number; // between 0.0 and 1.0 or 0 to 100
  className?: string;
  size?: 'sm' | 'md';
}

export const ConfidenceBadge: React.FC<ConfidenceBadgeProps> = ({
  confidence,
  className = '',
  size = 'md',
}) => {
  const normalized = confidence > 1 ? confidence : Math.round(confidence * 100);

  const getTheme = () => {
    if (normalized >= 85) {
      return {
        text: 'text-emerald-500',
        label: 'High',
      };
    }
    if (normalized >= 60) {
      return {
        text: 'text-[#9B8F77]',
        label: 'Med',
      };
    }
    return {
      text: 'text-amber-500',
      label: 'Low',
    };
  };

  const theme = getTheme();
  const sizeClasses = size === 'sm' ? 'px-1.5 py-0.5 text-[9px]' : 'px-2 py-0.5 text-[10px]';

  return (
    <span
      className={`inline-flex items-center gap-1.5 font-mono uppercase tracking-widest border border-border bg-card rounded-none ${sizeClasses} ${className}`}
    >
      <span className={`font-semibold ${theme.text}`}>{normalized}%</span>
      <span className="text-muted-foreground opacity-60">({theme.label})</span>
    </span>
  );
};
