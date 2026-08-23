import React, { useState, useEffect, useRef } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Database,
  Search,
  Layers,
  Sparkles,
  FileText,
  FileSpreadsheet,
  FileCode,
  ShieldCheck,
  ArrowLeft,
  ChevronRight,
  ChevronDown,
  Download,
  AlertTriangle,
  ArrowRight,
  Trash2,
  RefreshCw,
  Loader2
} from 'lucide-react';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { ConfidenceBadge } from '../../components/ui/ConfidenceBadge';
import { EnrichmentStepper } from '../../components/ui/EnrichmentStepper';
import { EnrichmentPanel } from './EnrichmentPanel';
import { ValidationPanel } from './ValidationPanel';
import { MultiSourceReconciliationPanel } from './MultiSourceReconciliationPanel';
import { formatAttrValueAndUnit } from '../../lib/formatters';
import { apiUrl } from '../../lib/api';

interface ProductItem {
  id: string;
  sku: string;
  brand: string;
  product_name: string;
  model?: string;
  category: string;
  status: string;
  quality_score: number;
  description?: string;
  commerce_description?: string;
  features?: string[];
  applications?: string[];
  keywords?: string[];
}

interface ProductAttributeItem {
  id: string;
  attribute_name: string;
  display_name: string;
  raw_value: string;
  normalized_value?: any;
  unit?: string;
  confidence: number;
  status: string;
}

interface EvidenceItem {
  id: string;
  attribute_id: string;
  page_number?: number;
  evidence_text: string;
  extraction_method: string;
}

export const ProductsShell: React.FC = () => {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const paramProductId = searchParams.get('product_id') || searchParams.get('product');

  const [selectedAttrId, setSelectedAttrId] = useState<string | null>(null);
  const [exportLoading, setExportLoading] = useState<boolean>(false);
  const [exportingFormat, setExportingFormat] = useState<string | null>(null);
  const [exportDropdownOpen, setExportDropdownOpen] = useState<boolean>(false);
  const [detailExportDropdownOpen, setDetailExportDropdownOpen] = useState<boolean>(false);
  const [clearingCatalog, setClearingCatalog] = useState<boolean>(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [clearError, setClearError] = useState<string | null>(null);

  const exportDropdownRef = useRef<HTMLDivElement>(null);
  const detailExportDropdownRef = useRef<HTMLDivElement>(null);

  // Filters
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [categoryFilter, setCategoryFilter] = useState<string>('all');

  // Detail Active Tab
  const [activeTab, setActiveTab] = useState<'enrichment' | 'attributes' | 'reconciliation' | 'validation'>('enrichment');

  // 1. Fetch Products List with React Query
  const {
    data: products = [],
    isLoading: loading,
    isFetching: isFetchingProducts,
    refetch: refetchProducts,
  } = useQuery<ProductItem[]>({
    queryKey: ['products-list'],
    queryFn: async () => {
      const res = await fetch(apiUrl('/api/v1/products?limit=50'));
      if (!res.ok) throw new Error('Failed to fetch products');
      return res.json();
    },
    staleTime: 30000,
  });

  const activeProductId = paramProductId || null;

  // 2. Fetch Selected Product Details with React Query (runs in parallel with product list)
  const {
    data: productDetailsData,
    isLoading: loadingDetails,
    isError: isDetailsError,
    error: detailsError,
  } = useQuery({
    queryKey: ['product-details', activeProductId],
    queryFn: async () => {
      if (!activeProductId) return null;
      const res = await fetch(apiUrl(`/api/v1/products/${activeProductId}/details`));
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Failed to fetch product details (HTTP ${res.status})`);
      }
      return res.json();
    },
    enabled: !!activeProductId,
    staleTime: 30000,
  });

  const selectedProduct: ProductItem | null = productDetailsData?.product || (productDetailsData?.id ? productDetailsData : null);
  const attributes: ProductAttributeItem[] = productDetailsData?.attributes || [];
  const evidenceList: EvidenceItem[] = productDetailsData?.evidence || [];
  const validationIssues: any[] = productDetailsData?.validation?.issues || productDetailsData?.validation_issues || [];
  const validationSummary: any = productDetailsData?.validation || null;
  const enrichmentData: any = productDetailsData?.enrichment || null;

  // Handle click outside of export dropdowns
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (exportDropdownRef.current && !exportDropdownRef.current.contains(event.target as Node)) {
        setExportDropdownOpen(false);
      }
      if (detailExportDropdownRef.current && !detailExportDropdownRef.current.contains(event.target as Node)) {
        setDetailExportDropdownOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleClearAllProducts = async () => {
    if (!window.confirm("Are you sure you want to reset the catalog? This will remove all products, extracted attributes, and validation records.")) {
      return;
    }
    try {
      setClearingCatalog(true);
      setClearError(null);
      setSuccessMessage(null);
      const res = await fetch(apiUrl('/api/v1/products/clear-all'), { method: 'DELETE' });
      if (!res.ok) {
        let errMsg = 'Failed to clear catalog';
        try {
          const errData = await res.json();
          if (errData.detail) errMsg = errData.detail;
        } catch {}
        throw new Error(errMsg);
      }
      const data = await res.json();
      setSuccessMessage(data.message || `Successfully reset catalog and cleared ${data.products_deleted ?? 0} products.`);
      queryClient.setQueryData(['products-list'], []);
      queryClient.removeQueries({ queryKey: ['product-details'] });
      queryClient.invalidateQueries({ queryKey: ['products-list'] });
      queryClient.invalidateQueries({ queryKey: ['overview-summary'] });
      queryClient.invalidateQueries({ queryKey: ['catalogHealth'] });
      queryClient.invalidateQueries({ queryKey: ['reviews-list'] });
      queryClient.invalidateQueries({ queryKey: ['processing-documents'] });
      queryClient.invalidateQueries({ queryKey: ['parsed-document'] });
      queryClient.invalidateQueries({ queryKey: ['search'] });
      queryClient.invalidateQueries({ queryKey: ['facets'] });
      queryClient.invalidateQueries({ queryKey: ['reconciliation'] });
      queryClient.invalidateQueries({ queryKey: ['sources'] });
      clearSelection();
    } catch (err: any) {
      console.error('Failed to clear catalog:', err);
      setClearError(err?.message || 'Error resetting catalog');
    } finally {
      setClearingCatalog(false);
    }
  };

  const selectProduct = (prod: ProductItem) => {
    setSelectedAttrId(null);
    setSearchParams({ product_id: prod.id });
  };

  const clearSelection = () => {
    setSelectedAttrId(null);
    setSearchParams({});
  };

  const handleRerunValidation = async () => {
    if (!selectedProduct) return;
    try {
      const res = await fetch(apiUrl(`/api/v1/products/${selectedProduct.id}/validate`), { method: 'POST' });
      if (res.ok) {
        queryClient.invalidateQueries({ queryKey: ['product-details', selectedProduct.id] });
        queryClient.invalidateQueries({ queryKey: ['products-list'] });
        queryClient.invalidateQueries({ queryKey: ['overview-summary'] });
        queryClient.invalidateQueries({ queryKey: ['catalogHealth'] });
        queryClient.invalidateQueries({ queryKey: ['reviews-list'] });
      }
    } catch (err) {
      console.error('Failed to rerun validation:', err);
    }
  };

  const handleRerunEnrichment = async () => {
    if (!selectedProduct) return;
    try {
      const res = await fetch(apiUrl(`/api/v1/products/${selectedProduct.id}/enrich`), { method: 'POST' });
      if (res.ok) {
        queryClient.invalidateQueries({ queryKey: ['product-details', selectedProduct.id] });
        queryClient.invalidateQueries({ queryKey: ['products-list'] });
        queryClient.invalidateQueries({ queryKey: ['overview-summary'] });
      }
    } catch (err) {
      console.error('Failed to rerun enrichment:', err);
    }
  };

  const handleExportCatalog = async (format: 'xlsx' | 'csv' | 'pdf' | 'json', targetProductId?: string) => {
    setExportingFormat(format);
    setExportLoading(true);
    try {
      const params = new URLSearchParams();
      params.append('format', format);
      if (targetProductId) {
        params.append('product_id', targetProductId);
      } else {
        if (statusFilter !== 'all') params.append('status', statusFilter);
        if (categoryFilter !== 'all') params.append('category', categoryFilter);
      }

      const res = await fetch(apiUrl(`/api/v1/products/export?${params.toString()}`));
      if (res.ok) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;

        // Determine filename
        let downloadName = '';
        const disposition = res.headers.get('Content-Disposition');
        if (disposition && disposition.includes('filename=')) {
          downloadName = disposition.split('filename=')[1].replace(/["']/g, '').trim();
        }
        if (!downloadName) {
          const skuSuffix = targetProductId && selectedProduct ? `_${selectedProduct.sku}` : '';
          const extMap: Record<string, string> = { xlsx: 'xlsx', csv: 'csv', pdf: 'pdf', json: 'json' };
          downloadName = `Unilog_Delivery${skuSuffix}_Format_252_Columns.${extMap[format] || format}`;
        }

        link.download = downloadName;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
      }
    } catch (err) {
      console.error('Failed to export catalog:', err);
    } finally {
      setExportLoading(false);
      setExportingFormat(null);
      setExportDropdownOpen(false);
      setDetailExportDropdownOpen(false);
    }
  };

  // Filter products
  const categories = Array.from(new Set(products.map((p) => p.category).filter(Boolean)));
  const filteredProducts = products.filter((p) => {
    const matchesSearch =
      !searchQuery ||
      p.product_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      p.sku.toLowerCase().includes(searchQuery.toLowerCase()) ||
      p.brand.toLowerCase().includes(searchQuery.toLowerCase());

    const matchesStatus =
      statusFilter === 'all' || p.status.toLowerCase() === statusFilter.toLowerCase();

    const matchesCategory =
      categoryFilter === 'all' || p.category.toLowerCase() === categoryFilter.toLowerCase();

    return matchesSearch && matchesStatus && matchesCategory;
  });

  const selectedEvidence = evidenceList.filter(
    (e) => !selectedAttrId || e.attribute_id === selectedAttrId
  );

  if (activeProductId && loadingDetails) {
    return (
      <div className="space-y-6 animate-pulse text-foreground">
        <div className="flex items-center justify-between">
          <div className="h-8 w-64 bg-card border border-border"></div>
          <div className="h-8 w-32 bg-card border border-border"></div>
        </div>
        <div className="h-48 border border-border bg-card"></div>
        <div className="h-96 border border-border bg-card"></div>
      </div>
    );
  }

  if (activeProductId && isDetailsError) {
    return (
      <div className="space-y-6 text-foreground">
        <div className="p-8 border border-destructive/30 bg-destructive/5 text-center space-y-4 rounded-none">
          <AlertTriangle className="w-12 h-12 text-destructive mx-auto" />
          <h3 className="font-serif text-xl font-normal text-foreground">Product Details Unavailable</h3>
          <p className="text-xs uppercase tracking-wider text-muted-foreground font-light">
            {(detailsError as Error)?.message || 'The requested product could not be loaded or was removed.'}
          </p>
          <button
            onClick={clearSelection}
            className="h-10 px-6 bg-foreground text-background border border-foreground hover:bg-transparent hover:text-foreground text-[10px] uppercase tracking-widest font-semibold transition duration-150 rounded-none inline-flex items-center gap-2"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Back to Product Catalog</span>
          </button>
        </div>
      </div>
    );
  }

  if (!activeProductId && loading) {
    return (
      <div className="space-y-6 animate-pulse text-foreground">
        <div className="h-8 w-64 bg-card border border-border"></div>
        <div className="h-96 border border-border bg-card"></div>
      </div>
    );
  }

  // ==========================================
  // 1. PRODUCT DETAIL CENTERPIECE VIEW
  // ==========================================
  if (selectedProduct) {
    const isNeedsReview = selectedProduct.status === 'needs_review';

    return (
      <div className="space-y-8 text-foreground rounded-none">
        {/* Navigation Breadcrumb & Actions Bar */}
        <div className="flex items-center justify-between flex-wrap gap-4">
          <button
            onClick={clearSelection}
            className="inline-flex items-center gap-2 text-xs uppercase tracking-widest font-light text-muted-foreground hover:text-foreground transition"
          >
            <ArrowLeft className="w-4 h-4 text-[#9B8F77]" />
            <span>Back to Product Catalog</span>
          </button>

          <div className="flex items-center gap-3 flex-wrap">
            {/* Unified Export Menu for Product */}
            <div className="relative" ref={detailExportDropdownRef}>
              <button
                onClick={() => setDetailExportDropdownOpen(!detailExportDropdownOpen)}
                disabled={exportLoading}
                className="h-9 px-4 border border-border bg-card text-foreground hover:bg-accent/40 text-[10px] uppercase tracking-widest font-semibold transition rounded-none inline-flex items-center gap-2 disabled:opacity-40"
              >
                {exportLoading ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin text-[#9B8F77]" />
                ) : (
                  <Download className="w-3.5 h-3.5 text-[#9B8F77]" />
                )}
                <span>Export Dossier</span>
                <ChevronDown className="w-3 h-3 text-muted-foreground" />
              </button>

              {detailExportDropdownOpen && (
                <div className="absolute right-0 mt-1 w-72 border border-border bg-card shadow-2xl z-50 rounded-none divide-y divide-border animate-in fade-in slide-in-from-top-1 duration-150">
                  <div className="p-3 bg-background/50">
                    <div className="text-[9px] font-mono uppercase tracking-widest text-[#9B8F77]">
                      Export Product Dossier
                    </div>
                    <div className="text-[11px] text-foreground font-serif">
                      SKU: {selectedProduct.sku}
                    </div>
                  </div>

                  <div className="p-1 space-y-0.5">
                    <button
                      onClick={() => handleExportCatalog('pdf', selectedProduct.id)}
                      className="w-full px-3 py-2.5 flex items-start gap-3 hover:bg-accent text-left transition rounded-none group"
                    >
                      <FileText className="w-4 h-4 text-red-500 mt-0.5 shrink-0" />
                      <div className="min-w-0 flex-1">
                        <div className="text-xs font-medium text-foreground flex items-center justify-between">
                          <span>PDF Spec Sheet</span>
                          <span className="text-[9px] font-mono px-1.5 py-0.2 border border-border bg-background text-red-500">PDF</span>
                        </div>
                        <div className="text-[10px] text-muted-foreground font-light">
                          Executive formatted product intelligence dossier
                        </div>
                      </div>
                    </button>

                    <button
                      onClick={() => handleExportCatalog('xlsx', selectedProduct.id)}
                      className="w-full px-3 py-2.5 flex items-start gap-3 hover:bg-accent text-left transition rounded-none group"
                    >
                      <FileSpreadsheet className="w-4 h-4 text-emerald-500 mt-0.5 shrink-0" />
                      <div className="min-w-0 flex-1">
                        <div className="text-xs font-medium text-foreground flex items-center justify-between">
                          <span>Excel Workbook</span>
                          <span className="text-[9px] font-mono px-1.5 py-0.2 border border-border bg-background text-emerald-500">XLSX</span>
                        </div>
                        <div className="text-[10px] text-muted-foreground font-light">
                          252-Column Unilog standard master row
                        </div>
                      </div>
                    </button>

                    <button
                      onClick={() => handleExportCatalog('csv', selectedProduct.id)}
                      className="w-full px-3 py-2.5 flex items-start gap-3 hover:bg-accent text-left transition rounded-none group"
                    >
                      <FileText className="w-4 h-4 text-blue-500 mt-0.5 shrink-0" />
                      <div className="min-w-0 flex-1">
                        <div className="text-xs font-medium text-foreground flex items-center justify-between">
                          <span>CSV Delivery Document</span>
                          <span className="text-[9px] font-mono px-1.5 py-0.2 border border-border bg-background text-blue-500">CSV</span>
                        </div>
                        <div className="text-[10px] text-muted-foreground font-light">
                          Standard comma-separated delivery dataset
                        </div>
                      </div>
                    </button>

                    <button
                      onClick={() => handleExportCatalog('json', selectedProduct.id)}
                      className="w-full px-3 py-2.5 flex items-start gap-3 hover:bg-accent text-left transition rounded-none group"
                    >
                      <FileCode className="w-4 h-4 text-amber-500 mt-0.5 shrink-0" />
                      <div className="min-w-0 flex-1">
                        <div className="text-xs font-medium text-foreground flex items-center justify-between">
                          <span>JSON Payload</span>
                          <span className="text-[9px] font-mono px-1.5 py-0.2 border border-border bg-background text-amber-500">JSON</span>
                        </div>
                        <div className="text-[10px] text-muted-foreground font-light">
                          Structured machine-readable normalized record
                        </div>
                      </div>
                    </button>
                  </div>
                </div>
              )}
            </div>

            <button
              onClick={handleRerunValidation}
              className="h-9 px-4 border border-border bg-card text-muted-foreground hover:text-foreground text-[10px] uppercase tracking-widest font-medium transition rounded-none"
            >
              Re-validate
            </button>
            <button
              onClick={handleRerunEnrichment}
              className="h-9 px-4 bg-foreground text-background border border-foreground hover:bg-transparent hover:text-foreground text-[10px] uppercase tracking-widest font-semibold transition rounded-none"
            >
              Re-enrich AI
            </button>
          </div>
        </div>

        {/* Needs Review Banner */}
        {isNeedsReview && (
          <div className="border border-amber-500/40 bg-amber-500/5 p-4 flex items-center justify-between rounded-none">
            <div className="flex items-center gap-3">
              <AlertTriangle className="w-5 h-5 text-amber-500" />
              <div>
                <div className="text-xs font-medium text-amber-500 uppercase tracking-wider">This product requires human review</div>
                <div className="text-[11px] text-muted-foreground font-light">
                  {validationIssues.length} validation issue{validationIssues.length !== 1 ? 's' : ''} found — see the Validation tab for details.
                </div>
              </div>
            </div>
            <Link
              to={`/reviews?product_id=${selectedProduct.id}`}
              className="h-9 px-4 bg-amber-500 text-white text-[10px] uppercase tracking-widest font-semibold transition rounded-none inline-flex items-center gap-1.5 hover:bg-amber-600 shrink-0"
            >
              <span>Go to Review</span>
              <ArrowRight className="w-3 h-3" />
            </Link>
          </div>
        )}

        {/* Product Identity Header Card */}
        <div className="border border-border bg-card p-6 md:p-8 rounded-none relative overflow-hidden space-y-4">
          <div className="flex flex-col md:flex-row md:items-start justify-between gap-6">
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-2.5">
                <span className="px-2.5 py-0.5 border border-border bg-background font-mono text-[10px] text-[#9B8F77]">
                  {selectedProduct.brand}
                </span>
                <span className="font-mono text-[11px] text-muted-foreground">
                  SKU: <strong className="text-foreground">{selectedProduct.sku}</strong>
                </span>
                {selectedProduct.model && (
                  <span className="font-mono text-[11px] text-muted-foreground">
                    Model: <strong className="text-foreground">{selectedProduct.model}</strong>
                  </span>
                )}
              </div>

              <h1 className="text-3xl sm:text-4xl font-serif font-normal text-foreground tracking-tight">
                {selectedProduct.product_name}
              </h1>

              <div className="flex items-center gap-4 text-xs text-muted-foreground font-light">
                <span>Category: <strong className="text-foreground font-medium">{selectedProduct.category}</strong></span>
                <span>•</span>
                <span>{attributes.length} Extracted Attributes</span>
              </div>
            </div>

            <div className="flex md:flex-col items-end gap-3 shrink-0">
              <StatusBadge status={selectedProduct.status} size="lg" />
              <div className="text-right">
                <div className="text-[9px] uppercase tracking-widest text-muted-foreground font-medium">
                  Catalog Quality
                </div>
                <div className="text-2xl font-serif font-normal text-emerald-500">
                  {Math.round(selectedProduct.quality_score)}%
                </div>
              </div>
            </div>
          </div>

          {/* Explainable Quality Score Breakdown Grid */}
          <div className="mt-4 pt-4 border-t border-border/80">
            <div className="text-[10px] uppercase tracking-widest font-mono text-[#9B8F77] mb-2.5 flex items-center justify-between">
              <span>Quality Score Breakdown & Provenance Dimensions</span>
              <span className="text-muted-foreground font-normal">Deterministic Dimension Scoring (100 pts max)</span>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2.5 text-xs">
              <div className="p-2.5 border border-border bg-background/60 space-y-1">
                <div className="text-[9px] uppercase tracking-wider text-muted-foreground">1. Identity</div>
                <div className="font-mono font-bold text-foreground">
                  {selectedProduct.brand && selectedProduct.sku ? '20' : '10'}/20
                </div>
                <div className="text-[9px] text-[#9B8F77]">Canonical MFR/Brand</div>
              </div>

              <div className="p-2.5 border border-border bg-background/60 space-y-1">
                <div className="text-[9px] uppercase tracking-wider text-muted-foreground">2. Taxonomy</div>
                <div className="font-mono font-bold text-foreground">
                  {selectedProduct.category && !selectedProduct.category.includes('General Supplies') ? '20' : '10'}/20
                </div>
                <div className="text-[9px] text-[#9B8F77]">Approved Classpath</div>
              </div>

              <div className="p-2.5 border border-border bg-background/60 space-y-1">
                <div className="text-[9px] uppercase tracking-wider text-muted-foreground">3. Attributes</div>
                <div className="font-mono font-bold text-foreground">
                  {Math.min(25, 10 + attributes.length * 3)}/25
                </div>
                <div className="text-[9px] text-[#9B8F77]">{attributes.length} Extracted Specs</div>
              </div>

              <div className="p-2.5 border border-border bg-background/60 space-y-1">
                <div className="text-[9px] uppercase tracking-wider text-muted-foreground">4. Evidence</div>
                <div className="font-mono font-bold text-foreground">
                  {evidenceList.length > 0 || attributes.some(a => a.attribute_name === 'MFR URL' || a.attribute_name === 'URL' || a.attribute_name === 'PDF Link') ? '15' : '10'}/15
                </div>
                <div className="text-[9px] text-[#9B8F77]">OEM Source Mapping</div>
              </div>

              <div className="p-2.5 border border-border bg-background/60 space-y-1">
                <div className="text-[9px] uppercase tracking-wider text-muted-foreground">5. Content</div>
                <div className="font-mono font-bold text-foreground">
                  {selectedProduct.commerce_description ? '10' : '5'}/10
                </div>
                <div className="text-[9px] text-[#9B8F77]">Commerce Summary</div>
              </div>

              <div className="p-2.5 border border-border bg-background/60 space-y-1">
                <div className="text-[9px] uppercase tracking-wider text-muted-foreground">6. Validation</div>
                <div className="font-mono font-bold text-foreground">
                  {Math.max(0, 10 - validationIssues.length * 5)}/10
                </div>
                <div className={`text-[9px] ${validationIssues.length === 0 ? 'text-emerald-500' : 'text-amber-500'}`}>
                  {validationIssues.length === 0 ? '0 Blocking Issues' : `${validationIssues.length} Open Issues`}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Visual Transformation Stepper */}
        <EnrichmentStepper
          status={selectedProduct.status}
          qualityScore={selectedProduct.quality_score}
        />

        {/* Tab Navigation */}
        <div className="flex border-b border-border gap-6 text-xs uppercase tracking-widest font-light">
          {[
            { id: 'enrichment', label: 'Commerce Intelligence', icon: Sparkles },
            { id: 'attributes', label: `Technical Specs (${attributes.length})`, icon: Layers },
            { id: 'reconciliation', label: 'Multi-Source Reconciliation', icon: Database },
            { id: 'validation', label: `Validation (${validationIssues.length})`, icon: ShieldCheck },
          ].map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={`pb-3 flex items-center gap-2 border-b-2 transition-all ${
                  isActive
                    ? 'border-foreground text-foreground font-medium'
                    : 'border-transparent text-muted-foreground hover:text-foreground'
                }`}
              >
                <Icon className="w-3.5 h-3.5 text-[#9B8F77]" />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </div>

        {/* Tab Contents */}
        {activeTab === 'enrichment' && (
          <EnrichmentPanel
            product={selectedProduct}
            attributes={attributes}
            enrichment={enrichmentData}
            onRerunEnrichment={handleRerunEnrichment}
          />
        )}

        {activeTab === 'attributes' && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Attributes Table */}
            <div className="lg:col-span-2 border border-border bg-card p-6 rounded-none space-y-4">
              <h3 className="font-serif text-xl font-normal text-foreground flex items-center gap-2 border-b border-border pb-3">
                <Layers className="w-4 h-4 text-[#9B8F77]" />
                <span>Extracted Engineering Attributes</span>
              </h3>

              <div className="divide-y divide-border">
                {attributes.map((attr) => {
                  const isSelected = selectedAttrId === attr.id;
                  const hasEvid = evidenceList.some((e) => e.attribute_id === attr.id);
                  const formatted = formatAttrValueAndUnit(attr.raw_value, attr.unit, attr.normalized_value);
                  return (
                    <div
                      key={attr.id}
                      onClick={() => setSelectedAttrId(isSelected ? null : attr.id)}
                      className={`py-3 px-3 flex items-center justify-between gap-4 cursor-pointer transition rounded-none ${
                        isSelected
                          ? 'bg-accent/60 border-l-2 border-foreground'
                          : 'hover:bg-accent/30'
                      }`}
                    >
                      <div className="space-y-0.5 min-w-0">
                        <div className="text-xs font-medium text-foreground flex items-center gap-2">
                          <span>{attr.display_name || attr.attribute_name}</span>
                          {hasEvid && (
                            <span className="text-[9px] font-mono text-[#9B8F77] px-1.5 py-0.2 border border-border bg-background">
                              Evidence
                            </span>
                          )}
                        </div>
                        <div className="text-xs font-mono text-muted-foreground">
                          {formatted.value} {formatted.unit && <span className="text-foreground">{formatted.unit}</span>}
                        </div>
                      </div>

                      <div className="flex items-center gap-3 shrink-0">
                        <ConfidenceBadge confidence={attr.confidence} size="sm" />
                        <StatusBadge status={attr.status} size="sm" />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Evidence Provenance Sidebar */}
            <div className="border border-border bg-card p-6 rounded-none space-y-4">
              <h3 className="font-serif text-xl font-normal text-foreground flex items-center gap-2 border-b border-border pb-3">
                <FileText className="w-4 h-4 text-[#9B8F77]" />
                <span>Evidence & Provenance</span>
              </h3>

              {selectedEvidence.length === 0 ? (
                <div className="py-12 text-center text-xs text-muted-foreground space-y-2 font-light uppercase tracking-wider">
                  <FileText className="w-8 h-8 mx-auto text-muted-foreground opacity-50" />
                  <p>Select an attribute to inspect verbatim source evidence citations.</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {selectedEvidence.map((evid) => (
                    <div key={evid.id} className="p-4 border border-border bg-background space-y-2 rounded-none">
                      <div className="flex items-center justify-between text-[10px] text-muted-foreground font-mono">
                        <span className="text-[#9B8F77]">
                          {evid.page_number ? `Page ${evid.page_number}` : 'Document Source'}
                        </span>
                        <span className="uppercase text-[9px]">
                          {evid.extraction_method}
                        </span>
                      </div>
                      <blockquote className="text-xs text-foreground italic border-l-2 border-[#9B8F77] pl-3 leading-relaxed font-light">
                        "{evid.evidence_text}"
                      </blockquote>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === 'reconciliation' && (
          <MultiSourceReconciliationPanel productId={selectedProduct.id} />
        )}

        {activeTab === 'validation' && (
          <ValidationPanel
            productId={selectedProduct.id}
            productStatus={selectedProduct.status}
            qualityScore={selectedProduct.quality_score}
            completenessScore={validationSummary?.completeness_score}
            issues={validationIssues}
            onResolutionCompleted={() => {
              refetchProducts();
              if (selectedProduct) {
                queryClient.invalidateQueries({ queryKey: ['product-details', selectedProduct.id] });
              }
              queryClient.invalidateQueries({ queryKey: ['overview-summary'] });
              queryClient.invalidateQueries({ queryKey: ['catalogHealth'] });
              queryClient.invalidateQueries({ queryKey: ['reviews-list'] });
            }}
          />
        )}
      </div>
    );
  }

  // ==========================================
  // 2. CATALOG TABLE & INVENTORY VIEW
  // ==========================================
  return (
    <div className="space-y-8 text-foreground rounded-none">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="space-y-1">
          <div className="inline-flex items-center gap-2 border border-[#9B8F77]/30 bg-[#9B8F77]/5 px-3 py-1 text-[9px] uppercase tracking-widest font-medium text-[#9B8F77] mb-2">
            <Database className="w-3.5 h-3.5" />
            Verified Master Catalog
          </div>
          <h1 className="text-3xl lg:text-4xl font-serif font-normal text-foreground tracking-tight">
            Product Catalog & Intelligence
          </h1>
          <p className="text-xs uppercase tracking-wider text-muted-foreground font-light">
            Browse and inspect all validated, quality-scored, and enriched industrial items.
          </p>
        </div>

        <div className="flex items-center gap-3 self-start sm:self-auto flex-wrap">
          {/* Consolidated Unified Export Hub Dropdown */}
          <div className="relative" ref={exportDropdownRef}>
            <button
              onClick={() => setExportDropdownOpen(!exportDropdownOpen)}
              disabled={exportLoading || products.length === 0}
              className="h-10 px-4 border border-border bg-card text-foreground hover:bg-accent/40 text-[10px] uppercase tracking-widest font-semibold transition duration-150 rounded-none inline-flex items-center gap-2 disabled:opacity-40"
              title="Export product catalog in standard formats"
            >
              {exportLoading ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin text-[#9B8F77]" />
              ) : (
                <Download className="w-3.5 h-3.5 text-[#9B8F77]" />
              )}
              <span>{exportLoading ? `Exporting ${exportingFormat?.toUpperCase()}...` : 'Export Catalog'}</span>
              <ChevronDown className={`w-3.5 h-3.5 text-muted-foreground transition-transform duration-150 ${exportDropdownOpen ? 'rotate-180' : ''}`} />
            </button>

            {exportDropdownOpen && (
              <div className="absolute right-0 mt-1 w-80 border border-border bg-card shadow-2xl z-50 rounded-none divide-y divide-border animate-in fade-in slide-in-from-top-1 duration-150">
                <div className="p-3 bg-background/50 flex items-center justify-between">
                  <div className="text-[9px] font-mono uppercase tracking-widest text-[#9B8F77]">
                    Unilog Master Delivery Export
                  </div>
                  <span className="text-[9px] font-mono text-muted-foreground">
                    252 Columns
                  </span>
                </div>

                <div className="p-1.5 space-y-0.5">
                  <button
                    onClick={() => handleExportCatalog('xlsx')}
                    className="w-full px-3 py-2.5 flex items-start gap-3 hover:bg-accent text-left transition rounded-none group"
                  >
                    <FileSpreadsheet className="w-4 h-4 text-emerald-500 mt-0.5 shrink-0" />
                    <div className="min-w-0 flex-1">
                      <div className="text-xs font-medium text-foreground flex items-center justify-between">
                        <span>Excel Spreadsheet</span>
                        <span className="text-[9px] font-mono px-1.5 py-0.2 border border-border bg-background text-emerald-500">.XLSX</span>
                      </div>
                      <div className="text-[10px] text-muted-foreground font-light">
                        Formatted workbook with 252 delivery headers
                      </div>
                    </div>
                  </button>

                  <button
                    onClick={() => handleExportCatalog('csv')}
                    className="w-full px-3 py-2.5 flex items-start gap-3 hover:bg-accent text-left transition rounded-none group"
                  >
                    <FileText className="w-4 h-4 text-blue-500 mt-0.5 shrink-0" />
                    <div className="min-w-0 flex-1">
                      <div className="text-xs font-medium text-foreground flex items-center justify-between">
                        <span>CSV Delivery File</span>
                        <span className="text-[9px] font-mono px-1.5 py-0.2 border border-border bg-background text-blue-500">.CSV</span>
                      </div>
                      <div className="text-[10px] text-muted-foreground font-light">
                        Standard comma-separated values client format
                      </div>
                    </div>
                  </button>

                  <button
                    onClick={() => handleExportCatalog('pdf')}
                    className="w-full px-3 py-2.5 flex items-start gap-3 hover:bg-accent text-left transition rounded-none group"
                  >
                    <FileText className="w-4 h-4 text-red-500 mt-0.5 shrink-0" />
                    <div className="min-w-0 flex-1">
                      <div className="text-xs font-medium text-foreground flex items-center justify-between">
                        <span>PDF Executive Report</span>
                        <span className="text-[9px] font-mono px-1.5 py-0.2 border border-border bg-background text-red-500">.PDF</span>
                      </div>
                      <div className="text-[10px] text-muted-foreground font-light">
                        Executive catalog dossier with KPIs and spec cards
                      </div>
                    </div>
                  </button>

                  <button
                    onClick={() => handleExportCatalog('json')}
                    className="w-full px-3 py-2.5 flex items-start gap-3 hover:bg-accent text-left transition rounded-none group"
                  >
                    <FileCode className="w-4 h-4 text-amber-500 mt-0.5 shrink-0" />
                    <div className="min-w-0 flex-1">
                      <div className="text-xs font-medium text-foreground flex items-center justify-between">
                        <span>JSON Master Dataset</span>
                        <span className="text-[9px] font-mono px-1.5 py-0.2 border border-border bg-background text-amber-500">.JSON</span>
                      </div>
                      <div className="text-[10px] text-muted-foreground font-light">
                        Full machine-readable catalog with metadata
                      </div>
                    </div>
                  </button>
                </div>
              </div>
            )}
          </div>

          <button
            onClick={() => refetchProducts()}
            className="h-10 px-4 border border-border bg-card text-muted-foreground hover:text-foreground text-[10px] uppercase tracking-widest font-medium transition duration-150 rounded-none inline-flex items-center gap-1.5"
            title="Refresh product list"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-[#9B8F77] ${isFetchingProducts ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>

          <button
            onClick={handleClearAllProducts}
            disabled={clearingCatalog || products.length === 0}
            className="h-10 px-4 border border-destructive/30 bg-destructive/5 text-destructive hover:bg-destructive hover:text-destructive-foreground text-[10px] uppercase tracking-widest font-medium transition duration-150 rounded-none inline-flex items-center gap-1.5 disabled:opacity-40"
            title="Reset catalog and clear all products"
          >
            <Trash2 className="w-3.5 h-3.5" />
            <span>{clearingCatalog ? 'Resetting...' : 'Reset Catalog'}</span>
          </button>

          <Link
            to="/upload"
            className="h-10 px-6 bg-foreground text-background border border-foreground hover:bg-transparent hover:text-foreground text-[10px] uppercase tracking-widest font-semibold transition duration-150 rounded-none inline-flex items-center gap-2"
          >
            <Sparkles className="w-3.5 h-3.5 text-[#9B8F77]" />
            <span>Import Catalog</span>
          </Link>
        </div>
      </div>

      {successMessage && (
        <div className="bg-emerald-500/10 border border-emerald-500/30 text-emerald-500 text-xs rounded-none p-4 flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Sparkles className="w-4 h-4 flex-shrink-0" />
            <span>{successMessage}</span>
          </div>
          <button onClick={() => setSuccessMessage(null)} className="text-muted-foreground hover:text-foreground text-xs">Dismiss</button>
        </div>
      )}

      {clearError && (
        <div className="bg-destructive/10 border border-destructive/20 text-destructive text-xs rounded-none p-4 flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <AlertTriangle className="w-4 h-4 flex-shrink-0" />
            <span>{clearError}</span>
          </div>
          <button onClick={() => setClearError(null)} className="text-muted-foreground hover:text-foreground text-xs">Dismiss</button>
        </div>
      )}

      {/* Filter Toolbar */}
      <div className="p-4 border border-border bg-card flex flex-wrap items-center justify-between gap-4 rounded-none">
        <div className="flex items-center gap-3 flex-1 min-w-[240px]">
          <div className="relative flex-1">
            <Search className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search products by SKU, Name, or Brand..."
              className="w-full pl-9 pr-4 py-2 bg-background border border-border text-xs text-foreground placeholder:text-muted-foreground outline-none focus:border-foreground transition rounded-none font-light"
            />
          </div>
        </div>

        <div className="flex items-center gap-3 flex-wrap">
          <div className="px-3 py-2 border border-border bg-background font-mono text-[10px] text-muted-foreground whitespace-nowrap">
            Showing <strong className="text-foreground">{filteredProducts.length}</strong> of <strong className="text-foreground">{products.length}</strong> Products
          </div>

          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-3 py-2 bg-background border border-border text-xs uppercase tracking-wider text-foreground outline-none rounded-none"
          >
            <option value="all">All Statuses</option>
            <option value="verified">Verified</option>
            <option value="needs_review">Needs Review</option>
            <option value="draft">Draft</option>
          </select>

          <select
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
            className="px-3 py-2 bg-background border border-border text-xs uppercase tracking-wider text-foreground outline-none rounded-none"
          >
            <option value="all">All Categories</option>
            {categories.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Catalog Table */}
      {filteredProducts.length === 0 ? (
        <div className="p-12 border border-border bg-card text-center space-y-4 rounded-none">
          <Database className="w-12 h-12 text-muted-foreground opacity-50 mx-auto" />
          <h3 className="font-serif text-xl font-normal text-foreground">
            {products.length === 0 ? 'No Products in Catalog' : 'No Matching Products Found'}
          </h3>
          <p className="text-xs uppercase tracking-wider text-muted-foreground font-light">
            {products.length === 0
              ? 'Upload a document to start building your product catalog.'
              : 'Try adjusting your search query or status filter.'}
          </p>
          {products.length === 0 && (
            <Link
              to="/upload"
              className="h-10 px-6 bg-foreground text-background border border-foreground hover:bg-transparent hover:text-foreground text-[10px] uppercase tracking-widest font-semibold transition duration-150 rounded-none inline-flex items-center gap-2"
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span>Upload Document</span>
            </Link>
          )}
        </div>
      ) : (
        <div className="border border-border bg-card overflow-hidden rounded-none">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-border bg-background/50 text-[9px] uppercase tracking-widest text-muted-foreground font-medium">
                  <th className="py-3.5 px-5">Product Details</th>
                  <th className="py-3.5 px-4">Brand</th>
                  <th className="py-3.5 px-4">SKU / MPN</th>
                  <th className="py-3.5 px-4">Category</th>
                  <th className="py-3.5 px-4">Quality Score</th>
                  <th className="py-3.5 px-4">Status</th>
                  <th className="py-3.5 px-4 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border text-xs">
                {filteredProducts.map((prod) => (
                  <tr
                    key={prod.id}
                    onClick={() => selectProduct(prod)}
                    className="hover:bg-accent/40 cursor-pointer transition group"
                  >
                    <td className="py-3.5 px-5">
                      <div className="font-medium text-foreground group-hover:text-[#9B8F77] transition">
                        {prod.product_name}
                      </div>
                    </td>
                    <td className="py-3.5 px-4 font-light text-muted-foreground">{prod.brand}</td>
                    <td className="py-3.5 px-4 font-mono text-muted-foreground">{prod.sku}</td>
                    <td className="py-3.5 px-4 text-muted-foreground font-light">{prod.category}</td>
                    <td className="py-3.5 px-4">
                      <ConfidenceBadge confidence={prod.quality_score} size="sm" />
                    </td>
                    <td className="py-3.5 px-4">
                      <StatusBadge status={prod.status} size="sm" />
                    </td>
                    <td className="py-3.5 px-4 text-right">
                      <button className="text-muted-foreground group-hover:text-foreground transition">
                        <ChevronRight className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
