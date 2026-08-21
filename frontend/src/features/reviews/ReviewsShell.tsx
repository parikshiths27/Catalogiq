import React, { useState, useEffect } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  AlertTriangle,
  Search,
  RefreshCw,
  CheckCircle2,
  X,
  ArrowRight,
  ShieldAlert,
  Info,
  Check,
  Tag,
  Clock,
  UserCheck
} from 'lucide-react';
import { ConfidenceBadge } from '../../components/ui/ConfidenceBadge';

interface EvidenceItem {
  id: string;
  attribute_id?: string;
  source_name: string;
  source_type: string;
  trust_level: number;
  document_filename?: string;
  page_number?: number;
  evidence_text: string;
  extraction_method: string;
}

interface ReviewItem {
  validation_id: string;
  product_id: string;
  product_name: string;
  brand: string;
  sku: string;
  category: string;
  attribute_id?: string;
  attribute_name?: string;
  display_name?: string;
  category_type: string;
  validation_type: string;
  status: string;
  severity: string;
  message: string;
  actual_value?: any;
  expected_value?: any;
  current_value?: any;
  confidence?: number;
  product_quality_score: number;
  created_at: string;
  resolved_at?: string;
  resolved_by?: string;
  evidence: EvidenceItem[];
  competing_claims: any[];
}

interface ReviewSummaryCounts {
  total_open_issues: number;
  total_resolved_issues?: number;
  cross_source_conflicts: number;
  low_confidence_issues: number;
  validation_issues: number;
  missing_required_attributes: number;
  products_needing_review: number;
}

interface ReviewsResponse {
  summary: ReviewSummaryCounts;
  items: ReviewItem[];
  total_items: number;
  page: number;
  limit: number;
  total_pages: number;
}

const VALIDATION_TYPE_META: Record<string, { label: string; explanation: string }> = {
  taxonomy_unresolved: {
    label: 'Taxonomy Classification Unresolved',
    explanation: 'The extracted product category is not present in the authoritative master taxonomy tree and requires mapping to an approved classpath.',
  },
  low_confidence: {
    label: 'Low Confidence Extraction',
    explanation: 'The AI model extracted this attribute with confidence below the 75% threshold, requiring human verification.',
  },
  missing_required_attribute: {
    label: 'Missing Required Attribute',
    explanation: 'A mandatory specification required for this category is missing from the document extraction.',
  },
  missing_attribute: {
    label: 'Missing Required Attribute',
    explanation: 'A mandatory specification required for this category is missing from the document extraction.',
  },
  missing_required_field: {
    label: 'Missing Mandatory Field',
    explanation: 'A core product field (SKU, Brand, or Product Name) could not be resolved with certainty.',
  },
  cross_source_conflict: {
    label: 'Multi-Source Conflict',
    explanation: 'Multiple documents or catalog sources provide contradictory values for this attribute.',
  },
  cross_attribute_conflict: {
    label: 'Attribute Conflict',
    explanation: 'Contradictory values detected across different attribute extractions.',
  },
  inconsistent_value: {
    label: 'Inconsistent Specification',
    explanation: 'Extracted attribute value does not match historical or catalog standards.',
  },
  range_violation: {
    label: 'Range Outlier',
    explanation: 'The extracted numerical value falls outside the plausible engineering range for this equipment.',
  },
  unsupported_claim: {
    label: 'Unverified Claim',
    explanation: 'No verbatim source citation or bounding text could be found to ground this extracted value.',
  },
};

export const ReviewsShell: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const paramProductId = searchParams.get('product_id');
  const paramIssueType = searchParams.get('issue_type');

  const [data, setData] = useState<ReviewsResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [statusFilter, setStatusFilter] = useState<string>('open');
  const [categoryFilter, setCategoryFilter] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');

  // Resolution modal state
  const [selectedReview, setSelectedReview] = useState<ReviewItem | null>(null);
  const [resolving, setResolving] = useState<boolean>(false);
  const [customValueInput, setCustomValueInput] = useState<string>('');
  const [showCustomInput, setShowCustomInput] = useState<boolean>(false);
  const [resolutionSuccess, setResolutionSuccess] = useState<string | null>(null);

  // Approved taxonomies list from backend
  const [approvedTaxonomies, setApprovedTaxonomies] = useState<string[]>([]);
  const [taxonomySearch, setTaxonomySearch] = useState<string>('');

  const fetchReviews = async () => {
    try {
      setLoading(true);
      setError(null);

      const params = new URLSearchParams();
      if (statusFilter !== 'all') params.append('status', statusFilter);
      if (categoryFilter !== 'all') params.append('category', categoryFilter);
      if (searchQuery.trim()) params.append('search', searchQuery.trim());
      if (paramProductId) params.append('product_id', paramProductId);
      if (paramIssueType) params.append('issue_type', paramIssueType);

      const res = await fetch(`/api/v1/reviews?${params.toString()}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const reviewData: ReviewsResponse = await res.json();
      setData(reviewData);
    } catch (err: any) {
      console.error('Failed to fetch reviews:', err);
      setError(err?.message || 'Failed to load review items');
    } finally {
      setLoading(false);
    }
  };

  const fetchApprovedTaxonomies = async () => {
    try {
      const res = await fetch('/api/v1/reviews/approved-taxonomies');
      if (res.ok) {
        const list: string[] = await res.json();
        setApprovedTaxonomies(list);
      }
    } catch (err) {
      console.error('Failed to fetch approved taxonomies:', err);
    }
  };

  useEffect(() => {
    fetchReviews();
  }, [statusFilter, categoryFilter, paramProductId, paramIssueType]);

  useEffect(() => {
    fetchApprovedTaxonomies();
  }, []);

  const handleResolve = async (action: 'accept_current' | 'override_custom') => {
    if (!selectedReview) return;
    setResolving(true);
    setResolutionSuccess(null);

    const isTaxonomyUnresolved = selectedReview.validation_type === 'taxonomy_unresolved';
    const effectiveVal = action === 'override_custom' ? customValueInput.trim() : String(selectedReview.actual_value || '');

    try {
      const payload: any = {
        action: isTaxonomyUnresolved ? 'override_custom' : action,
        resolved_value: effectiveVal,
      };

      const res = await fetch(`/api/v1/reviews/items/${selectedReview.validation_id}/resolve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        let errorMsg = `Resolution failed with HTTP ${res.status}`;
        try {
          const errBody = await res.json();
          if (typeof errBody?.detail === 'object' && errBody.detail?.message) {
            errorMsg = errBody.detail.message;
          } else if (typeof errBody?.detail === 'string') {
            errorMsg = errBody.detail;
          }
        } catch (_) {}
        throw new Error(errorMsg);
      }

      setResolutionSuccess('Issue resolved and verified successfully in database!');
      setTimeout(() => {
        setSelectedReview(null);
        setResolutionSuccess(null);
        fetchReviews();
      }, 1000);
    } catch (err: any) {
      alert(`Error resolving: ${err?.message}`);
    } finally {
      setResolving(false);
    }
  };

  const summary = data?.summary;
  const items = data?.items || [];

  // Dynamic categories from loaded review items
  const dynamicCategories = Array.from(new Set(items.map((i) => i.category).filter(Boolean)));

  const isSelectedTaxonomyUnresolved = selectedReview?.validation_type === 'taxonomy_unresolved';

  // Filtered approved taxonomies
  const filteredTaxonomies = approvedTaxonomies.filter((t) =>
    !taxonomySearch || t.toLowerCase().includes(taxonomySearch.toLowerCase())
  );

  return (
    <div className="space-y-8 text-foreground rounded-none">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="space-y-1">
          <div className="inline-flex items-center gap-2 border border-[#9B8F77]/30 bg-[#9B8F77]/5 px-3 py-1 text-[9px] uppercase tracking-widest font-medium text-[#9B8F77] mb-2">
            <AlertTriangle className="w-3.5 h-3.5" />
            Evidence-Based Quality Assurance
          </div>
          <h1 className="text-3xl lg:text-4xl font-serif font-normal text-foreground tracking-tight">
            Human Review & Quality Triage
          </h1>
          <p className="text-xs uppercase tracking-wider text-muted-foreground font-light">
            Every issue clearly explains why human attention is required, with verbatim source evidence citations and approved canonical values.
          </p>
        </div>

        <button
          onClick={fetchReviews}
          className="h-10 px-4 border border-border bg-card text-muted-foreground hover:text-foreground text-xs uppercase tracking-widest font-medium transition rounded-none flex items-center gap-2 self-start sm:self-auto"
          title="Refresh Review Queue"
        >
          <RefreshCw className="w-3.5 h-3.5 text-[#9B8F77]" />
          <span>Refresh</span>
        </button>
      </div>

      {/* Active Product / Issue Type Filter Banner */}
      {(paramProductId || paramIssueType) && (
        <div className="p-3.5 border border-[#9B8F77]/40 bg-[#9B8F77]/10 flex items-center justify-between gap-4 rounded-none text-xs">
          <div className="flex items-center gap-2">
            <ShieldAlert className="w-4 h-4 text-[#9B8F77] shrink-0" />
            <span>
              Filtered for: {paramProductId && <strong className="font-mono">Product ID: {paramProductId.slice(0, 8)}...</strong>}
              {paramProductId && paramIssueType && ' • '}
              {paramIssueType && <strong className="font-mono uppercase">Issue: {paramIssueType}</strong>}
            </span>
          </div>
          <button
            onClick={() => setSearchParams({})}
            className="text-[10px] uppercase tracking-widest font-semibold text-[#9B8F77] hover:text-foreground inline-flex items-center gap-1"
          >
            <X className="w-3.5 h-3.5" />
            <span>Clear Filter</span>
          </button>
        </div>
      )}

      {/* Summary KPI Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="p-5 border border-border bg-card rounded-none space-y-1">
          <div className="text-2xl font-serif font-normal text-amber-500">
            {summary?.total_open_issues ?? 0}
          </div>
          <div className="text-[9px] font-medium text-muted-foreground uppercase tracking-widest">
            Total Open Issues
          </div>
        </div>

        <div className="p-5 border border-border bg-card rounded-none space-y-1">
          <div className="text-2xl font-serif font-normal text-emerald-500">
            {summary?.total_resolved_issues ?? 0}
          </div>
          <div className="text-[9px] font-medium text-muted-foreground uppercase tracking-widest">
            Resolved Issues
          </div>
        </div>

        <div className="p-5 border border-border bg-card rounded-none space-y-1">
          <div className="text-2xl font-serif font-normal text-destructive">
            {summary?.cross_source_conflicts ?? 0}
          </div>
          <div className="text-[9px] font-medium text-muted-foreground uppercase tracking-widest">
            Reconciliation Conflicts
          </div>
        </div>

        <div className="p-5 border border-border bg-card rounded-none space-y-1">
          <div className="text-2xl font-serif font-normal text-foreground">
            {summary?.products_needing_review ?? 0}
          </div>
          <div className="text-[9px] font-medium text-muted-foreground uppercase tracking-widest">
            Products Needing Review
          </div>
        </div>
      </div>

      {/* Filter Bar & Tabs */}
      <div className="p-4 border border-border bg-card flex flex-wrap items-center justify-between gap-4 rounded-none">
        <div className="flex items-center gap-3 flex-1 min-w-[240px]">
          <div className="relative flex-1">
            <Search className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && fetchReviews()}
              placeholder="Search by product name, SKU, or attribute..."
              className="w-full pl-9 pr-4 py-2 bg-background border border-border text-xs text-foreground placeholder:text-muted-foreground outline-none focus:border-foreground transition rounded-none font-light"
            />
          </div>
        </div>

        <div className="flex items-center gap-3">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-3 py-2 bg-background border border-border text-xs uppercase tracking-wider text-foreground outline-none rounded-none font-medium"
          >
            <option value="open">Open Issues ({summary?.total_open_issues ?? 0})</option>
            <option value="resolved">Resolved Issues ({summary?.total_resolved_issues ?? 0})</option>
            <option value="all">All Issues</option>
          </select>

          <select
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
            className="px-3 py-2 bg-background border border-border text-xs uppercase tracking-wider text-foreground outline-none rounded-none"
          >
            <option value="all">All Categories</option>
            {dynamicCategories.map((cat) => (
              <option key={cat} value={cat}>
                {cat}
              </option>
            ))}
          </select>
        </div>
      </div>

      {error && (
        <div className="p-4 border border-destructive/40 bg-destructive/10 flex items-center gap-3 text-xs text-destructive rounded-none">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Review Queue Items */}
      {loading ? (
        <div className="space-y-4 animate-pulse">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-32 border border-border bg-card rounded-none"></div>
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="p-12 border border-border bg-card text-center space-y-4 rounded-none">
          <CheckCircle2 className="w-12 h-12 text-emerald-500 mx-auto" />
          <h3 className="font-serif text-xl font-normal text-foreground">
            {statusFilter === 'resolved' ? 'No Resolved Issues Found' : 'Review Queue is Clean'}
          </h3>
          <p className="text-xs uppercase tracking-wider text-muted-foreground font-light">
            {statusFilter === 'resolved'
              ? 'Issues resolved by human reviewers will appear here with full audit trail history.'
              : 'No products currently require manual verification or conflict resolution.'}
          </p>
          <Link
            to="/catalog"
            className="h-10 px-6 bg-foreground text-background border border-foreground hover:bg-transparent hover:text-foreground text-[10px] uppercase tracking-widest font-semibold transition duration-150 rounded-none inline-flex items-center gap-2"
          >
            <span>Explore Product Catalog</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      ) : (
        <div className="space-y-4">
          {items.map((item) => {
            const meta = VALIDATION_TYPE_META[item.validation_type] || {
              label: item.validation_type.replace(/_/g, ' '),
              explanation: 'Specification requires human verification.',
            };

            const isResolved = item.status === 'resolved';

            return (
              <div
                key={item.validation_id}
                className={`p-6 border bg-card space-y-4 rounded-none transition ${
                  isResolved ? 'border-emerald-500/40 bg-emerald-500/5' : 'border-border hover:border-muted-foreground'
                }`}
              >
                {/* Product Identity Header */}
                <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-[10px] text-[#9B8F77] px-2 py-0.5 border border-border bg-background">
                        {item.brand}
                      </span>
                      <span className="font-mono text-xs text-muted-foreground">SKU: {item.sku}</span>
                      <span className="text-xs text-muted-foreground">•</span>
                      <span className="text-xs text-muted-foreground font-light">{item.category}</span>
                    </div>
                    <h3 className="font-serif text-xl font-normal text-foreground">{item.product_name}</h3>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    {isResolved ? (
                      <span className="inline-flex items-center gap-1.5 px-3 py-1 bg-emerald-500/10 border border-emerald-500/40 text-emerald-500 text-[10px] uppercase tracking-widest font-mono font-bold">
                        <Check className="w-3.5 h-3.5" />
                        Resolved
                      </span>
                    ) : (
                      <>
                        {item.confidence != null && <ConfidenceBadge confidence={item.confidence} />}
                        <span
                          className={`text-[9px] font-mono uppercase tracking-widest px-2.5 py-1 border rounded-none ${
                            item.severity === 'error'
                              ? 'border-destructive/40 bg-destructive/10 text-destructive'
                              : 'border-amber-500/40 bg-amber-500/10 text-amber-500'
                          }`}
                        >
                          {meta.label}
                        </span>
                      </>
                    )}
                  </div>
                </div>

                {/* WHY REASONING BANNER */}
                <div className={`p-3.5 border space-y-1 rounded-none text-xs ${
                  isResolved ? 'border-emerald-500/30 bg-background' : 'border-amber-500/40 bg-amber-500/5'
                }`}>
                  <div className="flex items-center gap-2 font-medium uppercase tracking-wide text-amber-500">
                    <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                    <span>Issue Description</span>
                  </div>
                  <p className="text-foreground font-light leading-relaxed">{item.message}</p>
                  <p className="text-[11px] text-muted-foreground font-light flex items-center gap-1.5 pt-0.5">
                    <Info className="w-3 h-3 text-[#9B8F77] shrink-0" />
                    {meta.explanation}
                  </p>

                  {/* Resolution History if resolved */}
                  {isResolved && (
                    <div className="mt-2 pt-2 border-t border-border flex flex-wrap items-center gap-4 text-xs font-mono text-emerald-400">
                      <span className="inline-flex items-center gap-1">
                        <UserCheck className="w-3.5 h-3.5" />
                        Resolved Value: <strong>{String(item.actual_value || item.current_value)}</strong>
                      </span>
                      {item.resolved_at && (
                        <span className="inline-flex items-center gap-1 text-muted-foreground">
                          <Clock className="w-3.5 h-3.5" />
                          {new Date(item.resolved_at).toLocaleString()}
                        </span>
                      )}
                    </div>
                  )}

                  {!isResolved && item.attribute_name && (
                    <div className="text-[10px] text-muted-foreground font-mono pt-1">
                      Target Attribute: <strong className="text-foreground">{item.display_name || item.attribute_name}</strong>
                      {item.actual_value != null && (
                        <span> • Extracted Value: <strong className="text-foreground">{String(item.actual_value)}</strong></span>
                      )}
                    </div>
                  )}
                </div>

                {/* Evidence Quote */}
                {item.evidence && item.evidence.length > 0 && (
                  <div className="p-3 border border-border bg-card/60 text-xs space-y-1 rounded-none">
                    <div className="text-[9px] font-medium uppercase tracking-widest text-muted-foreground flex items-center justify-between">
                      <span>Source Document Evidence Citation</span>
                      <span className="font-mono text-[#9B8F77]">
                        {item.evidence[0].source_name || 'Document'} {item.evidence[0].page_number ? `(Page ${item.evidence[0].page_number})` : ''}
                      </span>
                    </div>
                    <blockquote className="text-foreground italic border-l-2 border-[#9B8F77] pl-2.5 font-light">
                      "{item.evidence[0].evidence_text}"
                    </blockquote>
                  </div>
                )}

                {/* Action Toolbar */}
                <div className="pt-2 flex items-center justify-between border-t border-border">
                  <Link
                    to={`/catalog?product_id=${item.product_id}`}
                    className="text-xs uppercase tracking-widest font-light text-muted-foreground hover:text-foreground inline-flex items-center gap-1 transition"
                  >
                    <span>Inspect in Master Catalog</span>
                    <ArrowRight className="w-3.5 h-3.5 text-[#9B8F77]" />
                  </Link>

                  {!isResolved && (
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => {
                          setSelectedReview(item);
                          setCustomValueInput(String(item.actual_value || ''));
                          setShowCustomInput(item.validation_type === 'taxonomy_unresolved');
                          setTaxonomySearch('');
                        }}
                        className="h-9 px-4 bg-foreground text-background border border-foreground hover:bg-transparent hover:text-foreground text-[10px] uppercase tracking-widest font-semibold transition duration-150 rounded-none"
                      >
                        Resolve Issue
                      </button>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Resolution Modal */}
      {selectedReview && (
        <div className="fixed inset-0 bg-background/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="p-6 md:p-8 border border-border bg-card max-w-xl w-full space-y-6 shadow-2xl relative rounded-none max-h-[90vh] overflow-y-auto">
            <button
              onClick={() => setSelectedReview(null)}
              className="absolute top-4 right-4 text-muted-foreground hover:text-foreground p-1"
            >
              <X className="w-5 h-5" />
            </button>

            <div>
              <span className="text-[9px] font-mono uppercase tracking-widest text-[#9B8F77]">
                Human Issue Resolution
              </span>
              <h3 className="font-serif text-2xl font-normal text-foreground mt-1">
                {selectedReview.display_name || selectedReview.attribute_name || 'Taxonomy / Specification Review'}
              </h3>
              <p className="text-xs text-muted-foreground mt-1 font-light">{selectedReview.product_name}</p>
            </div>

            <div className="p-3.5 border border-border bg-background text-xs text-foreground rounded-none">
              {selectedReview.message}
            </div>

            {/* Current Value Display */}
            <div className="p-3.5 border border-border bg-background/80 space-y-1.5 rounded-none text-xs">
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground font-light uppercase tracking-wider text-[10px]">
                  Current Extracted Value:
                </span>
                {isSelectedTaxonomyUnresolved && (
                  <span className="text-destructive font-semibold text-[10px] inline-flex items-center gap-1">
                    <X className="w-3.5 h-3.5" /> Not in Authoritative Taxonomy
                  </span>
                )}
              </div>
              <div className="font-mono font-bold text-foreground break-all">
                {String(selectedReview.actual_value || selectedReview.current_value || 'None')}
              </div>
            </div>

            {/* If taxonomy_unresolved: show searchable approved classpaths */}
            {isSelectedTaxonomyUnresolved ? (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <label className="text-xs uppercase tracking-widest font-medium text-[#9B8F77] flex items-center gap-1.5">
                    <Tag className="w-3.5 h-3.5" />
                    Select Approved Taxonomy Classpath:
                  </label>
                  <span className="text-[10px] font-mono text-muted-foreground">
                    {approvedTaxonomies.length} available
                  </span>
                </div>

                <div className="relative">
                  <Search className="w-3.5 h-3.5 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
                  <input
                    type="text"
                    value={taxonomySearch}
                    onChange={(e) => setTaxonomySearch(e.target.value)}
                    placeholder="Search approved classpaths (e.g. Abrasives, Dishwashers, Drills)..."
                    className="w-full pl-8 pr-3 py-2 bg-background border border-border text-xs text-foreground placeholder:text-muted-foreground outline-none focus:border-foreground rounded-none font-mono"
                  />
                </div>

                <div className="max-h-48 overflow-y-auto border border-border bg-background divide-y divide-border rounded-none">
                  {filteredTaxonomies.slice(0, 30).map((cp) => {
                    const isSelected = customValueInput === cp;
                    return (
                      <button
                        key={cp}
                        type="button"
                        onClick={() => setCustomValueInput(cp)}
                        className={`w-full text-left px-3 py-2 text-xs font-mono transition flex items-center justify-between ${
                          isSelected ? 'bg-emerald-500/20 text-emerald-400 font-bold' : 'hover:bg-card text-foreground'
                        }`}
                      >
                        <span className="truncate pr-2">{cp}</span>
                        {isSelected && <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0" />}
                      </button>
                    );
                  })}
                </div>

                {customValueInput && (
                  <div className="p-2.5 border border-emerald-500/40 bg-emerald-500/10 text-xs font-mono text-emerald-400">
                    Selected: <strong>{customValueInput}</strong>
                  </div>
                )}
              </div>
            ) : showCustomInput ? (
              <div className="space-y-2">
                <label className="text-xs uppercase tracking-widest font-light text-muted-foreground">
                  Enter Verified Custom Value:
                </label>
                <input
                  type="text"
                  value={customValueInput}
                  onChange={(e) => setCustomValueInput(e.target.value)}
                  className="w-full px-3.5 py-2 bg-background border border-border text-xs text-foreground outline-none focus:border-foreground rounded-none font-mono"
                />
              </div>
            ) : null}

            {resolutionSuccess && (
              <div className="p-3 border border-emerald-500/40 bg-emerald-500/10 text-xs text-emerald-500 text-center font-mono rounded-none">
                {resolutionSuccess}
              </div>
            )}

            {/* Action Buttons */}
            <div className="flex flex-col gap-2.5 pt-2">
              {isSelectedTaxonomyUnresolved ? (
                <>
                  <button
                    onClick={() => handleResolve('override_custom')}
                    disabled={resolving || !customValueInput.trim()}
                    className="w-full h-10 bg-emerald-600 hover:bg-emerald-500 text-white text-[10px] uppercase tracking-widest font-semibold transition duration-150 rounded-none disabled:opacity-40"
                  >
                    {resolving ? 'Saving & Revalidating...' : 'Choose Approved Value & Save'}
                  </button>
                  <button
                    onClick={() => setSelectedReview(null)}
                    className="w-full h-10 border border-border bg-background text-muted-foreground hover:text-foreground hover:bg-card text-[10px] uppercase tracking-widest font-semibold transition duration-150 rounded-none"
                  >
                    Cancel
                  </button>
                </>
              ) : !showCustomInput ? (
                <>
                  <button
                    onClick={() => handleResolve('accept_current')}
                    disabled={resolving}
                    className="w-full h-10 bg-foreground text-background border border-foreground hover:bg-transparent hover:text-foreground text-[10px] uppercase tracking-widest font-semibold transition duration-150 rounded-none disabled:opacity-50"
                  >
                    Accept Current Value
                  </button>
                  <button
                    onClick={() => setShowCustomInput(true)}
                    className="w-full h-10 border border-border bg-background text-muted-foreground hover:text-foreground hover:bg-card text-[10px] uppercase tracking-widest font-semibold transition duration-150 rounded-none"
                  >
                    Override with Verified Value
                  </button>
                </>
              ) : (
                <>
                  <button
                    onClick={() => handleResolve('override_custom')}
                    disabled={resolving || !customValueInput.trim()}
                    className="w-full h-10 bg-emerald-600 hover:bg-emerald-500 text-white text-[10px] uppercase tracking-widest font-semibold transition duration-150 rounded-none disabled:opacity-50"
                  >
                    Save Verified Override
                  </button>
                  <button
                    onClick={() => setShowCustomInput(false)}
                    className="w-full h-10 border border-border bg-background text-muted-foreground hover:text-foreground hover:bg-card text-[10px] uppercase tracking-widest font-semibold transition duration-150 rounded-none"
                  >
                    Back
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
