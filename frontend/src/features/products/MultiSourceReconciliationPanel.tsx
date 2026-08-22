import React, { useState, useEffect } from 'react';
import {
  Layers,
  CheckCircle2,
  AlertTriangle,
  HelpCircle,
  FileText,
  ShieldCheck,
  ChevronDown,
  ChevronUp,
  Globe,
  Database,
  Info,
  Scale,
  RefreshCw,
  ExternalLink,
} from 'lucide-react';
import { apiUrl } from '../../lib/api';

export interface SourceClaim {
  source_id: string;
  source_name: string;
  source_type: string;
  trust_level: number;
  document_id?: string | null;
  page_number?: number | null;
  evidence_text?: string | null;
  attribute_id?: string | null;
  raw_value?: string | null;
  normalized_value?: number | string | null;
  unit?: string | null;
  extraction_method?: string | null;
}

export interface AttributeReconciliation {
  attribute_name: string;
  display_name: string;
  canonical_value: string;
  canonical_unit?: string | null;
  canonical_normalized_value?: number | string | null;
  status: 'AGREEMENT' | 'EQUIVALENT' | 'MISSING' | 'CONFLICTING';
  confidence_score: number;
  winning_source_name: string;
  winning_source_trust: number;
  claims: SourceClaim[];
  competing_claims: SourceClaim[];
  explanation?: string | null;
}

export interface ProductReconciliationData {
  product_id: string;
  product_name: string;
  total_attributes: number;
  agreements_count: number;
  equivalents_count: number;
  missing_count: number;
  conflicts_count: number;
  review_count: number;
  overall_confidence: number;
  reconciled_attributes: Record<string, AttributeReconciliation>;
}

export interface ProductSource {
  source_id: string;
  source_name: string;
  source_type: string;
  uri?: string | null;
  trust_level: number;
  document_id?: string | null;
  metadata_json?: Record<string, any> | null;
  created_at?: string | null;
  association_type?: string | null;
}

interface MultiSourceReconciliationPanelProps {
  productId: string;
  onRefreshRequested?: () => void;
}

export const MultiSourceReconciliationPanel: React.FC<MultiSourceReconciliationPanelProps> = ({
  productId,
  onRefreshRequested,
}) => {
  const [data, setData] = useState<ProductReconciliationData | null>(null);
  const [sources, setSources] = useState<ProductSource[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [expandedAttrs, setExpandedAttrs] = useState<Record<string, boolean>>({});
  const [showSourcesList, setShowSourcesList] = useState<boolean>(false);

  useEffect(() => {
    if (productId) {
      fetchReconciliationData();
    }
  }, [productId]);

  const fetchReconciliationData = async () => {
    try {
      setLoading(true);
      setError(null);

      const [recRes, srcRes] = await Promise.all([
        fetch(apiUrl(`/api/v1/products/${productId}/reconciliation`)),
        fetch(apiUrl(`/api/v1/products/${productId}/sources`)),
      ]);

      if (!recRes.ok) {
        throw new Error(`Reconciliation API returned status ${recRes.status}`);
      }

      const recData: ProductReconciliationData = await recRes.json();
      setData(recData);

      if (srcRes.ok) {
        const srcData: ProductSource[] = await srcRes.json();
        setSources(srcData);
      }

      // Default expand CONFLICTING attributes for immediate visual attention
      const initialExpanded: Record<string, boolean> = {};
      if (recData.reconciled_attributes) {
        Object.entries(recData.reconciled_attributes).forEach(([key, attr]) => {
          if (attr.status === 'CONFLICTING') {
            initialExpanded[key] = true;
          }
        });
      }
      setExpandedAttrs(initialExpanded);
    } catch (err: any) {
      console.error('Failed to fetch multi-source reconciliation data:', err);
      setError(err.message || 'Failed to load multi-source reconciliation intelligence');
    } finally {
      setLoading(false);
    }
  };

  const toggleExpand = (attrKey: string) => {
    setExpandedAttrs((prev) => ({
      ...prev,
      [attrKey]: !prev[attrKey],
    }));
  };

  const getStatusBadge = (status: AttributeReconciliation['status']) => {
    switch (status) {
      case 'AGREEMENT':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded bg-emerald-500/10 text-emerald-500 border border-emerald-500/20 text-xs font-semibold font-mono">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
            AGREEMENT
          </span>
        );
      case 'EQUIVALENT':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded bg-sky-950 text-sky-300 border border-sky-800 text-xs font-semibold font-mono">
            <Scale className="w-3.5 h-3.5 text-sky-400" />
            EQUIVALENT
          </span>
        );
      case 'MISSING':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded bg-accent text-foreground border border-border text-xs font-semibold font-mono">
            <HelpCircle className="w-3.5 h-3.5 text-muted-foreground" />
            NON-CONFLICTING (MISSING)
          </span>
        );
      case 'CONFLICTING':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded bg-red-500/10 text-red-500 border border-red-500/20 text-xs font-semibold font-mono animate-pulse">
            <AlertTriangle className="w-3.5 h-3.5 text-red-400" />
            CONFLICTING
          </span>
        );
      default:
        return null;
    }
  };

  const getSourceIcon = (sourceType: string) => {
    switch (sourceType) {
      case 'document':
        return <FileText className="w-3.5 h-3.5 text-foreground font-medium" />;
      case 'manufacturer_website':
        return <Globe className="w-3.5 h-3.5 text-emerald-400" />;
      case 'catalog':
      case 'supplier_feed':
        return <Database className="w-3.5 h-3.5 text-amber-400" />;
      default:
        return <Info className="w-3.5 h-3.5 text-muted-foreground" />;
    }
  };

  if (loading) {
    return (
      <div className="bg-card border border-border rounded-xl p-8 text-center text-muted-foreground space-y-3">
        <RefreshCw className="w-6 h-6 text-foreground font-medium animate-spin mx-auto" />
        <p className="text-sm font-medium">Reconciling multi-source intelligence & claim provenance...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-card border border-border rounded-xl p-6 space-y-3">
        <div className="flex items-center justify-between">
          <h4 className="text-base font-bold text-red-400 flex items-center gap-2">
            <AlertTriangle className="w-5 h-5" /> Multi-Source Reconciliation Unavailable
          </h4>
          <button
            onClick={fetchReconciliationData}
            className="px-3 py-1 bg-accent hover:bg-card text-foreground text-xs rounded border border-border transition"
          >
            Retry
          </button>
        </div>
        <p className="text-xs text-muted-foreground">{error}</p>
      </div>
    );
  }

  if (!data || Object.keys(data.reconciled_attributes).length === 0) {
    return (
      <div className="bg-card border border-border rounded-xl p-8 text-center text-muted-foreground space-y-2">
        <Layers className="w-8 h-8 text-muted-foreground mx-auto" />
        <h4 className="font-semibold text-foreground text-sm">No Reconciled Multi-Source Attributes</h4>
        <p className="text-xs max-w-sm mx-auto text-muted-foreground">
          This product does not currently have cross-source attribute claims registered for reconciliation.
        </p>
      </div>
    );
  }

  const attributesList = Object.values(data.reconciled_attributes);
  const filteredAttributes = attributesList.filter((attr) => {
    if (statusFilter === 'ALL') return true;
    return attr.status === statusFilter;
  });

  return (
    <div className="bg-card border border-border rounded-xl p-6 shadow-xl space-y-6 text-foreground">
      {/* Panel Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border pb-4">
        <div>
          <h3 className="text-lg font-bold text-foreground flex items-center gap-2">
            <Layers className="w-5 h-5 text-foreground font-medium" />
            <span>Multi-Source Intelligence & Specification Reconciliation</span>
          </h3>
          <p className="text-xs text-muted-foreground mt-1">
            Automated claim provenance analysis, unit equivalence verification, and cross-source conflict detection.
          </p>
        </div>

        <div className="flex items-center gap-2 self-start sm:self-auto">
          <button
            onClick={() => {
              fetchReconciliationData();
              if (onRefreshRequested) onRefreshRequested();
            }}
            className="px-3 py-1.5 bg-accent hover:bg-card text-foreground text-xs font-semibold rounded-lg border border-border transition flex items-center gap-1.5"
            title="Refresh reconciliation matrix"
          >
            <RefreshCw className="w-3.5 h-3.5 text-foreground font-medium" />
            <span>Refresh Matrix</span>
          </button>
        </div>
      </div>

      {/* Summary KPI Cards Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        {/* Overall Confidence Score */}
        <div className="bg-background border border-border rounded-lg p-3 space-y-1">
          <span className="text-[10px] font-semibold uppercase text-muted-foreground tracking-wider font-mono">
            Confidence Score
          </span>
          <div className="text-2xl font-black text-foreground font-medium">
            {Math.round(data.overall_confidence * 100)}%
          </div>
          <span className="text-[10px] text-muted-foreground font-mono block">Backend Authoritative</span>
        </div>

        {/* Total Attributes */}
        <div className="bg-background border border-border rounded-lg p-3 space-y-1">
          <span className="text-[10px] font-semibold uppercase text-muted-foreground tracking-wider font-mono">
            Total Attributes
          </span>
          <div className="text-2xl font-black text-foreground">{data.total_attributes}</div>
          <span className="text-[10px] text-muted-foreground font-mono block">Evaluated Specs</span>
        </div>

        {/* Agreements */}
        <div className="bg-background border border-border rounded-lg p-3 space-y-1">
          <span className="text-[10px] font-semibold uppercase text-emerald-400 tracking-wider font-mono">
            Agreements
          </span>
          <div className="text-2xl font-black text-emerald-400">{data.agreements_count}</div>
          <span className="text-[10px] text-emerald-500/80 font-mono block">Consensus Values</span>
        </div>

        {/* Equivalents */}
        <div className="bg-background border border-border rounded-lg p-3 space-y-1">
          <span className="text-[10px] font-semibold uppercase text-sky-400 tracking-wider font-mono">
            Equivalents
          </span>
          <div className="text-2xl font-black text-sky-400">{data.equivalents_count}</div>
          <span className="text-[10px] text-sky-500/80 font-mono block">SI Unit Matches</span>
        </div>

        {/* Missing */}
        <div className="bg-background border border-border rounded-lg p-3 space-y-1">
          <span className="text-[10px] font-semibold uppercase text-muted-foreground tracking-wider font-mono">
            Missing
          </span>
          <div className="text-2xl font-black text-foreground">{data.missing_count}</div>
          <span className="text-[10px] text-muted-foreground font-mono block">Non-Conflicting</span>
        </div>

        {/* Conflicts */}
        <div className={`bg-background border rounded-lg p-3 space-y-1 ${data.conflicts_count > 0 ? 'border-red-500/20/80 bg-red-500/10/20' : 'border-border'}`}>
          <span className={`text-[10px] font-semibold uppercase tracking-wider font-mono ${data.conflicts_count > 0 ? 'text-red-400' : 'text-muted-foreground'}`}>
            Conflicts
          </span>
          <div className={`text-2xl font-black ${data.conflicts_count > 0 ? 'text-red-400 animate-pulse' : 'text-muted-foreground'}`}>
            {data.conflicts_count}
          </div>
          <span className="text-[10px] text-muted-foreground font-mono block">Requires Review</span>
        </div>
      </div>

      {/* Filter Tabs & Controls */}
      <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
        <div className="flex items-center gap-1 bg-background p-1 rounded-lg border border-border text-xs">
          {[
            { id: 'ALL', label: `All (${attributesList.length})` },
            { id: 'CONFLICTING', label: `Conflicts (${data.conflicts_count})` },
            { id: 'AGREEMENT', label: `Agreements (${data.agreements_count})` },
            { id: 'EQUIVALENT', label: `Equivalents (${data.equivalents_count})` },
            { id: 'MISSING', label: `Missing (${data.missing_count})` },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setStatusFilter(tab.id)}
              className={`px-3 py-1.5 rounded-md font-semibold font-mono transition ${
                statusFilter === tab.id
                  ? 'bg-foreground text-background text-white shadow-sm'
                  : 'text-muted-foreground hover:text-foreground hover:bg-card'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <button
          onClick={() => setShowSourcesList(!showSourcesList)}
          className="px-3 py-1.5 bg-background hover:bg-accent text-foreground text-xs font-semibold rounded-lg border border-border transition flex items-center gap-1.5"
        >
          <Database className="w-3.5 h-3.5 text-foreground font-medium" />
          <span>Associated Sources ({sources.length})</span>
          {showSourcesList ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
        </button>
      </div>

      {/* Associated Sources Drawer Section */}
      {showSourcesList && (
        <div className="bg-background border border-border rounded-xl p-4 space-y-3">
          <h4 className="text-xs font-bold uppercase tracking-wider text-foreground font-mono flex items-center gap-2">
            <Database className="w-4 h-4 text-foreground font-medium" />
            Associated Specification Sources & Trust Hierarchy
          </h4>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {sources.map((src) => (
              <div
                key={src.source_id}
                className="bg-card border border-border rounded-lg p-3 space-y-2 text-xs"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5 font-semibold text-foreground">
                    {getSourceIcon(src.source_type)}
                    <span className="truncate max-w-[160px]">{src.source_name}</span>
                  </div>
                  <span className="px-2 py-0.5 bg-accent text-foreground border border-border rounded font-mono font-bold text-[11px]">
                    {Math.round(src.trust_level * 100)}% Trust
                  </span>
                </div>
                <div className="text-[11px] text-muted-foreground font-mono flex items-center justify-between">
                  <span className="capitalize">{src.source_type.replace('_', ' ')}</span>
                  {src.uri && (
                    <a
                      href={src.uri}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-foreground font-medium hover:text-foreground flex items-center gap-0.5"
                    >
                      <span>Link</span>
                      <ExternalLink className="w-3 h-3" />
                    </a>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Attribute Reconciliation Matrix List */}
      <div className="space-y-4">
        {filteredAttributes.length === 0 ? (
          <div className="p-8 text-center text-muted-foreground text-xs italic">
            No attributes match the selected filter category ({statusFilter}).
          </div>
        ) : (
          filteredAttributes.map((attr) => {
            const isExpanded = !!expandedAttrs[attr.attribute_name];
            const isConflict = attr.status === 'CONFLICTING';
            const isEquivalent = attr.status === 'EQUIVALENT';

            return (
              <div
                key={attr.attribute_name}
                className={`border rounded-xl transition overflow-hidden ${
                  isConflict
                    ? 'border-red-500/20/80 bg-red-500/10/10 shadow-lg shadow-red-950/20'
                    : isEquivalent
                    ? 'border-sky-900/60 bg-background/40'
                    : 'border-border bg-background/60'
                }`}
              >
                {/* Header Row */}
                <div
                  onClick={() => toggleExpand(attr.attribute_name)}
                  className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 cursor-pointer hover:bg-accent/30 transition"
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h4 className="text-base font-bold text-white">{attr.display_name}</h4>
                      {getStatusBadge(attr.status)}
                    </div>
                    <div className="flex items-center gap-3 text-xs text-muted-foreground font-mono">
                      <span>
                        Canonical Value:{' '}
                        <strong className="text-emerald-400 font-sans font-black text-sm">
                          {attr.canonical_value}
                        </strong>
                      </span>
                      {attr.canonical_unit && <span>Unit: {attr.canonical_unit}</span>}
                    </div>
                  </div>

                  <div className="flex items-center gap-4 self-end sm:self-auto">
                    <div className="text-right">
                      <div className="text-xs font-semibold text-foreground flex items-center gap-1 justify-end font-mono">
                        <ShieldCheck className="w-3.5 h-3.5 text-foreground font-medium" />
                        <span>Winning: {attr.winning_source_name}</span>
                      </div>
                      <div className="text-[11px] text-muted-foreground font-mono">
                        Source Trust: <span className="text-foreground font-bold">{Math.round(attr.winning_source_trust * 100)}%</span> | Confidence: <span className="text-emerald-400 font-bold">{Math.round(attr.confidence_score * 100)}%</span>
                      </div>
                    </div>
                    <button className="text-muted-foreground hover:text-foreground">
                      {isExpanded ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
                    </button>
                  </div>
                </div>

                {/* Explanation Banner for Conflicts & Unit Equivalence */}
                {attr.explanation && (
                  <div
                    className={`px-4 py-2 text-xs font-mono border-t ${
                      isConflict
                        ? 'bg-red-500/10/40 text-red-200 border-red-900/60'
                        : isEquivalent
                        ? 'bg-sky-950/30 text-sky-200 border-sky-900/40'
                        : 'bg-card/80 text-foreground border-border'
                    }`}
                  >
                    <span className="font-bold mr-1">Analysis:</span> {attr.explanation}
                  </div>
                )}

                {/* Detailed Claims Breakdown (Expanded View) */}
                {isExpanded && (
                  <div className="p-4 border-t border-border bg-card/70 space-y-4">
                    {/* Visual Comparison Section for CONFLICTING attributes */}
                    {isConflict && (
                      <div className="bg-red-500/10/30 border border-red-500/20/80 rounded-lg p-4 space-y-3">
                        <div className="flex items-center justify-between">
                          <h5 className="text-xs font-bold uppercase tracking-wider text-red-500 font-mono flex items-center gap-1.5">
                            <AlertTriangle className="w-4 h-4 text-red-400" />
                            Cross-Source Disagreement — Human Review Required
                          </h5>
                          <span className="text-[11px] bg-red-900/80 text-red-200 px-2 py-0.5 rounded font-mono font-semibold">
                            Conflict Identified
                          </span>
                        </div>

                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                          {/* Winning Claim Card */}
                          {attr.claims.slice(0, 1).map((claim) => (
                            <div
                              key={claim.source_id}
                              className="bg-background border-2 border-emerald-600 rounded-lg p-3 space-y-2 relative"
                            >
                              <div className="flex items-center justify-between">
                                <span className="text-[10px] font-black uppercase px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-500 border border-emerald-500/20 font-mono">
                                  Highest Trust Winner ({Math.round(claim.trust_level * 100)}%)
                                </span>
                                <span className="text-xs font-mono text-muted-foreground">{claim.source_type}</span>
                              </div>
                              <div className="font-bold text-white text-base">{claim.source_name}</div>
                              <div className="text-xl font-black text-emerald-400 font-mono">
                                {claim.raw_value || '—'}
                              </div>
                              {claim.evidence_text && (
                                <p className="text-[11px] text-foreground italic font-mono bg-card p-2 rounded border border-border">
                                  "{claim.evidence_text}"
                                </p>
                              )}
                            </div>
                          ))}

                          {/* Competing Claims Card */}
                          {attr.competing_claims.map((comp) => (
                            <div
                              key={comp.source_id}
                              className="bg-background border-2 border-red-700/80 rounded-lg p-3 space-y-2 relative"
                            >
                              <div className="flex items-center justify-between">
                                <span className="text-[10px] font-black uppercase px-2 py-0.5 rounded bg-red-500/10 text-red-500 border border-red-500/20 font-mono">
                                  Competing Claim ({Math.round(comp.trust_level * 100)}%)
                                </span>
                                <span className="text-xs font-mono text-muted-foreground">{comp.source_type}</span>
                              </div>
                              <div className="font-bold text-white text-base">{comp.source_name}</div>
                              <div className="text-xl font-black text-red-400 font-mono">
                                {comp.raw_value || '—'}
                              </div>
                              {comp.evidence_text && (
                                <p className="text-[11px] text-foreground italic font-mono bg-card p-2 rounded border border-border">
                                  "{comp.evidence_text}"
                                </p>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Claims Provenance Table */}
                    <div className="space-y-2">
                      <h5 className="text-xs font-bold uppercase tracking-wider text-muted-foreground font-mono">
                        All Reconciled Source Claims ({attr.claims.length})
                      </h5>
                      <div className="overflow-x-auto">
                        <table className="w-full text-left text-xs">
                          <thead>
                            <tr className="border-b border-border text-[11px] font-semibold uppercase text-muted-foreground font-mono">
                              <th className="py-2 px-2">Source</th>
                              <th className="py-2 px-2">Trust Level</th>
                              <th className="py-2 px-2">Extracted Value</th>
                              <th className="py-2 px-2">Normalized</th>
                              <th className="py-2 px-2">Evidence Text</th>
                              <th className="py-2 px-2">Location</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-border font-mono">
                            {attr.claims.map((claim, idx) => {
                              const isWinner = claim.source_name === attr.winning_source_name;

                              return (
                                <tr
                                  key={idx}
                                  className={isWinner ? 'bg-emerald-500/10/20 font-semibold' : 'hover:bg-accent/40'}
                                >
                                  <td className="py-2.5 px-2 font-sans font-bold text-foreground flex items-center gap-1.5">
                                    {getSourceIcon(claim.source_type)}
                                    <span>{claim.source_name}</span>
                                    {isWinner && (
                                      <span className="text-[9px] px-1.5 py-0.2 rounded bg-emerald-900 text-emerald-200 border border-emerald-700">
                                        WINNER
                                      </span>
                                    )}
                                  </td>
                                  <td className="py-2.5 px-2 font-bold text-foreground">
                                    {Math.round(claim.trust_level * 100)}%
                                  </td>
                                  <td className="py-2.5 px-2 text-emerald-400 font-bold">
                                    {claim.raw_value || '—'}
                                  </td>
                                  <td className="py-2.5 px-2 text-foreground">
                                    {claim.normalized_value !== null && claim.normalized_value !== undefined
                                      ? `${claim.normalized_value} ${claim.unit || ''}`
                                      : '—'}
                                  </td>
                                  <td className="py-2.5 px-2 text-foreground italic max-w-xs truncate" title={claim.evidence_text || ''}>
                                    "{claim.evidence_text || '—'}"
                                  </td>
                                  <td className="py-2.5 px-2 text-muted-foreground">
                                    {claim.page_number ? `Page ${claim.page_number}` : 'Website/Feed'}
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
