import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { ShieldCheck, CheckCircle2, Loader2, AlertTriangle, ArrowRight, Info } from 'lucide-react';

interface ValidationIssue {
  id?: string;
  validation_type: string;
  severity: string;
  attribute_name?: string;
  message: string;
  expected_value?: any;
  actual_value?: any;
}

interface ValidationPanelProps {
  productId: string;
  productStatus?: string;
  qualityScore: number;
  completenessScore?: number;
  issues: ValidationIssue[];
  onResolutionCompleted?: () => void;
}

const VALIDATION_TYPE_LABELS: Record<string, { label: string; description: string }> = {
  low_confidence: {
    label: 'Low Confidence Extraction',
    description: 'The AI model extracted this value with confidence below the 75% threshold, meaning it may be inaccurate.',
  },
  missing_attribute: {
    label: 'Missing Required Attribute',
    description: 'A mandatory attribute for this product category is missing and must be provided.',
  },
  cross_source_conflict: {
    label: 'Cross-Source Conflict',
    description: 'Multiple source documents provide different values for the same attribute.',
  },
  range_violation: {
    label: 'Range Violation',
    description: 'The extracted value falls outside the expected range for this attribute type.',
  },
  unit_mismatch: {
    label: 'Unit Mismatch',
    description: 'The unit of measurement does not match the expected standard for this attribute.',
  },
  semantic_inconsistency: {
    label: 'Semantic Inconsistency',
    description: 'The value does not semantically align with the attribute name or product category.',
  },
  completeness_gap: {
    label: 'Completeness Gap',
    description: 'Product data is incomplete — important optional attributes are missing.',
  },
  duplicate_value: {
    label: 'Duplicate Value',
    description: 'The same value appears across multiple different attributes.',
  },
};

export const ValidationPanel: React.FC<ValidationPanelProps> = ({
  productId,
  productStatus,
  qualityScore,
  completenessScore,
  issues,
  onResolutionCompleted,
}) => {
  const [resolvingId, setResolvingId] = useState<string | null>(null);
  const needsReview = productStatus === 'needs_review';

  const handleResolve = async (issueId: string, resolution: string, value?: any) => {
    try {
      setResolvingId(issueId);
      const res = await fetch(`/api/v1/products/${productId}/validation/${issueId}/resolve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          resolution,
          resolved_value: value,
          notes: `Resolved via UI with ${resolution}`,
        }),
      });

      if (res.ok) {
        if (onResolutionCompleted) {
          onResolutionCompleted();
        }
      }
    } catch (err) {
      console.error('Failed to resolve validation issue:', err);
    } finally {
      setResolvingId(null);
    }
  };

  // Group issues by type for the "Why Needs Review" section
  const issuesByType: Record<string, ValidationIssue[]> = {};
  issues.forEach((iss) => {
    const key = iss.validation_type || 'unknown';
    if (!issuesByType[key]) issuesByType[key] = [];
    issuesByType[key].push(iss);
  });

  return (
    <div className="border border-border bg-card p-6 space-y-6 rounded-none text-foreground">
      {/* Header & Quality Score */}
      <div className="flex items-center justify-between border-b border-border pb-4">
        <div>
          <h3 className="text-xl font-serif font-normal text-foreground flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-[#9B8F77]" />
            <span>Validation & Intelligence Health</span>
          </h3>
          <p className="text-xs uppercase tracking-wider text-muted-foreground mt-1 font-light">
            Deterministic rule checks, completeness scoring, and conflict management
          </p>
        </div>
        <div className="flex items-center gap-4">
          {completenessScore != null && (
            <div className="text-right">
              <span className="text-[9px] font-medium uppercase tracking-widest text-muted-foreground block">Completeness</span>
              <span className="text-base font-mono font-medium text-foreground">{completenessScore}%</span>
            </div>
          )}
          <div className="text-right border border-border bg-background px-3 py-1.5 rounded-none">
            <span className="text-[9px] font-medium uppercase tracking-widest text-muted-foreground block">Quality Score</span>
            <span className="text-xl font-serif font-normal text-emerald-500">{Math.round(qualityScore)}/100</span>
          </div>
        </div>
      </div>

      {/* WHY THIS PRODUCT NEEDS REVIEW — Prominent Section */}
      {needsReview && issues.length > 0 && (
        <div className="border border-amber-500/40 bg-amber-500/5 p-5 space-y-4 rounded-none">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-medium text-amber-500 flex items-center gap-2 uppercase tracking-wider">
              <AlertTriangle className="w-4 h-4" />
              Why This Product Needs Human Review
            </h4>
            <Link
              to={`/reviews?product_id=${productId}`}
              className="h-8 px-3 bg-amber-500 text-white text-[10px] uppercase tracking-widest font-semibold transition rounded-none inline-flex items-center gap-1.5 hover:bg-amber-600"
            >
              <span>Open in Review Queue</span>
              <ArrowRight className="w-3 h-3" />
            </Link>
          </div>

          <div className="space-y-3">
            {Object.entries(issuesByType).map(([type, typeIssues]) => {
              const meta = VALIDATION_TYPE_LABELS[type] || { label: type.replace(/_/g, ' '), description: '' };
              return (
                <div key={type} className="p-3 border border-border bg-background rounded-none space-y-1.5">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] font-mono uppercase tracking-widest px-2 py-0.5 border border-amber-500/40 bg-amber-500/10 text-amber-500 font-semibold">
                        {meta.label}
                      </span>
                      <span className="text-[10px] font-mono text-muted-foreground">
                        {typeIssues.length} issue{typeIssues.length > 1 ? 's' : ''}
                      </span>
                    </div>
                  </div>
                  {meta.description && (
                    <p className="text-[11px] text-muted-foreground font-light flex items-start gap-1.5">
                      <Info className="w-3 h-3 text-[#9B8F77] shrink-0 mt-0.5" />
                      {meta.description}
                    </p>
                  )}
                  <ul className="space-y-1 pl-1">
                    {typeIssues.map((iss, i) => (
                      <li key={iss.id || i} className="text-xs text-foreground font-light flex items-start gap-2">
                        <span className="text-amber-500 mt-0.5">•</span>
                        <span>
                          {iss.message}
                          {iss.attribute_name && (
                            <span className="text-muted-foreground font-mono ml-1">({iss.attribute_name})</span>
                          )}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Issues List */}
      {issues.length === 0 ? (
        <div className="border border-emerald-500/30 bg-emerald-500/5 p-4 text-emerald-500 flex items-center gap-3 rounded-none">
          <CheckCircle2 className="w-4 h-4 shrink-0" />
          <div>
            <p className="font-serif text-sm font-normal">No Validation Issues Detected</p>
            <p className="text-xs font-light opacity-80">Product data is complete, verified, and conflict-free.</p>
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          <h4 className="text-[10px] font-medium uppercase tracking-widest text-muted-foreground">
            All Validation Issues ({issues.length})
          </h4>
          {issues.map((iss, i) => {
            const meta = VALIDATION_TYPE_LABELS[iss.validation_type] || { label: iss.validation_type.replace(/_/g, ' '), description: '' };
            return (
              <div
                key={iss.id || i}
                className="border border-border bg-background p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4 rounded-none"
              >
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className={`text-[9px] font-mono uppercase tracking-widest px-2 py-0.5 border rounded-none ${
                      iss.severity === 'error'
                        ? 'border-destructive/40 bg-destructive/10 text-destructive'
                        : 'border-amber-500/40 bg-amber-500/10 text-amber-500'
                    }`}>
                      {meta.label}
                    </span>
                    {iss.attribute_name && (
                      <span className="font-mono text-xs text-muted-foreground">
                        Attribute: <strong className="text-foreground">{iss.attribute_name}</strong>
                      </span>
                    )}
                  </div>
                  <div className="text-xs font-light text-foreground">{iss.message}</div>
                  {iss.actual_value != null && (
                    <div className="text-[10px] font-mono text-muted-foreground">
                      Current value: <span className="text-foreground">{String(iss.actual_value)}</span>
                    </div>
                  )}
                </div>

                {iss.id && (
                  <div className="flex items-center gap-2 shrink-0">
                    <button
                      onClick={() => handleResolve(iss.id!, 'accept_actual', iss.actual_value)}
                      disabled={resolvingId === iss.id}
                      className="h-8 px-3 bg-foreground text-background border border-foreground hover:bg-transparent hover:text-foreground text-[9px] uppercase tracking-widest font-semibold transition rounded-none disabled:opacity-50"
                    >
                      {resolvingId === iss.id ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Accept Value'}
                    </button>
                    <button
                      onClick={() => handleResolve(iss.id!, 'dismiss')}
                      disabled={resolvingId === iss.id}
                      className="h-8 px-3 border border-border bg-card text-muted-foreground hover:text-foreground text-[9px] uppercase tracking-widest font-medium transition rounded-none disabled:opacity-50"
                    >
                      Dismiss
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
