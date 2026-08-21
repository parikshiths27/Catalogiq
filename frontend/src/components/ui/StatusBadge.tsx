import React from 'react';

export type ProductStatusType = 'verified' | 'needs_review' | 'draft' | 'invalid' | 'processing' | string;

interface StatusBadgeProps {
  status: ProductStatusType;
  className?: string;
  size?: 'sm' | 'md' | 'lg';
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({
  status,
  className = '',
  size = 'md',
}) => {
  const norm = (status || '').toLowerCase().trim();

  const sizeClasses = {
    sm: 'px-2 py-0.5 text-[9px]',
    md: 'px-2.5 py-1 text-[10px]',
    lg: 'px-3 py-1.5 text-xs',
  }[size];

  switch (norm) {
    case 'verified':
    case 'completed':
    case 'valid':
      return (
        <span
          className={`inline-flex items-center gap-1.5 font-mono uppercase tracking-widest font-medium border border-border bg-card text-emerald-500 rounded-none ${sizeClasses} ${className}`}
        >
          <span className="w-1.5 h-1.5 bg-emerald-500 rounded-none" />
          <span>Verified</span>
        </span>
      );

    case 'needs_review':
    case 'partially_completed':
      return (
        <span
          className={`inline-flex items-center gap-1.5 font-mono uppercase tracking-widest font-medium border border-border bg-card text-amber-500 rounded-none ${sizeClasses} ${className}`}
        >
          <span className="w-1.5 h-1.5 bg-amber-500 rounded-none" />
          <span>Needs Review</span>
        </span>
      );

    case 'draft':
    case 'queued':
      return (
        <span
          className={`inline-flex items-center gap-1.5 font-mono uppercase tracking-widest font-medium border border-border bg-card text-muted-foreground rounded-none ${sizeClasses} ${className}`}
        >
          <span className="w-1.5 h-1.5 bg-muted-foreground rounded-none" />
          <span>Draft</span>
        </span>
      );

    case 'invalid':
    case 'failed':
      return (
        <span
          className={`inline-flex items-center gap-1.5 font-mono uppercase tracking-widest font-medium border border-destructive/40 bg-destructive/10 text-destructive rounded-none ${sizeClasses} ${className}`}
        >
          <span className="w-1.5 h-1.5 bg-destructive rounded-none" />
          <span>Invalid</span>
        </span>
      );

    case 'processing':
    case 'parsing':
    case 'extracting':
      return (
        <span
          className={`inline-flex items-center gap-1.5 font-mono uppercase tracking-widest font-medium border border-border bg-card text-[#9B8F77] rounded-none ${sizeClasses} ${className}`}
        >
          <span className="w-1.5 h-1.5 bg-[#9B8F77] animate-pulse rounded-none" />
          <span className="capitalize">{norm}</span>
        </span>
      );

    default:
      return (
        <span
          className={`inline-flex items-center gap-1.5 font-mono uppercase tracking-widest font-medium border border-border bg-card text-muted-foreground rounded-none ${sizeClasses} ${className}`}
        >
          <span className="w-1.5 h-1.5 bg-muted-foreground rounded-none" />
          <span className="capitalize">{norm || 'Unknown'}</span>
        </span>
      );
  }
};
