import React, { useState, useEffect } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import {
  Database,
  Search,
  Layers,
  Sparkles,
  FileText,
  ShieldCheck,
  ArrowLeft,
  ChevronRight,
  Download,
  AlertTriangle,
  ArrowRight
} from 'lucide-react';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { ConfidenceBadge } from '../../components/ui/ConfidenceBadge';
import { EnrichmentStepper } from '../../components/ui/EnrichmentStepper';
import { EnrichmentPanel } from './EnrichmentPanel';
import { ValidationPanel } from './ValidationPanel';
import { MultiSourceReconciliationPanel } from './MultiSourceReconciliationPanel';
import { formatAttrValueAndUnit } from '../../lib/formatters';

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
  const [searchParams, setSearchParams] = useSearchParams();
  const paramProductId = searchParams.get('product_id') || searchParams.get('product');

  const [products, setProducts] = useState<ProductItem[]>([]);
  const [selectedProduct, setSelectedProduct] = useState<ProductItem | null>(null);
  const [attributes, setAttributes] = useState<ProductAttributeItem[]>([]);
  const [evidenceList, setEvidenceList] = useState<EvidenceItem[]>([]);
  const [validationIssues, setValidationIssues] = useState<any[]>([]);
  const [enrichmentData, setEnrichmentData] = useState<any>(null);
  const [validationSummary, setValidationSummary] = useState<any>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [selectedAttrId, setSelectedAttrId] = useState<string | null>(null);
  const [exportLoading, setExportLoading] = useState<boolean>(false);

  // Filters
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [categoryFilter, setCategoryFilter] = useState<string>('all');

  // Detail Active Tab
  const [activeTab, setActiveTab] = useState<'enrichment' | 'attributes' | 'reconciliation' | 'validation'>('enrichment');

  useEffect(() => {
    fetchProducts();
  }, []);

  const fetchProducts = async () => {
    try {
      setLoading(true);
      const res = await fetch('/api/v1/products');
      if (res.ok) {
        const data: ProductItem[] = await res.json();
        setProducts(data);

        if (paramProductId) {
          const match = data.find((p) => p.id === paramProductId);
          if (match) selectProduct(match);
        }
      }
    } catch (err) {
      console.error('Failed to fetch products:', err);
    } finally {
      setLoading(false);
    }
  };

  const selectProduct = async (prod: ProductItem) => {
    setSelectedProduct(prod);
    setSelectedAttrId(null);
    setSearchParams({ product_id: prod.id });

    try {
      const [attrRes, evidRes, valRes, enrichRes] = await Promise.all([
        fetch(`/api/v1/products/${prod.id}/attributes`),
        fetch(`/api/v1/products/${prod.id}/evidence`),
        fetch(`/api/v1/products/${prod.id}/validation`),
        fetch(`/api/v1/products/${prod.id}/enrichment`),
      ]);

      if (attrRes.ok) setAttributes(await attrRes.json());
      if (evidRes.ok) setEvidenceList(await evidRes.json());
      if (valRes.ok) {
        const valData = await valRes.json();
        setValidationIssues(valData.issues || []);
        setValidationSummary(valData);
      }
      if (enrichRes.ok) setEnrichmentData(await enrichRes.json());
    } catch (err) {
      console.error('Failed to fetch product details:', err);
    }
  };

  const clearSelection = () => {
    setSelectedProduct(null);
    setSearchParams({});
  };

  const handleRerunValidation = async () => {
    if (!selectedProduct) return;
    try {
      const res = await fetch(`/api/v1/products/${selectedProduct.id}/validate`, { method: 'POST' });
      if (res.ok) selectProduct(selectedProduct);
    } catch (err) {
      console.error('Failed to rerun validation:', err);
    }
  };

  const handleRerunEnrichment = async () => {
    if (!selectedProduct) return;
    try {
      const res = await fetch(`/api/v1/products/${selectedProduct.id}/enrich`, { method: 'POST' });
      if (res.ok) selectProduct(selectedProduct);
    } catch (err) {
      console.error('Failed to rerun enrichment:', err);
    }
  };

  const handleExportCatalog = async (format: string = 'xlsx') => {
    setExportLoading(true);
    try {
      const params = new URLSearchParams();
      params.append('format', format);
      if (statusFilter !== 'all') params.append('status', statusFilter);
      if (categoryFilter !== 'all') params.append('category', categoryFilter);

      const res = await fetch(`/api/v1/products/export?${params.toString()}`);
      if (res.ok) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = format === 'xlsx' ? 'CatalogIQ_Export.xlsx' : 'CatalogIQ_Export.csv';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
      }
    } catch (err) {
      console.error('Failed to export catalog:', err);
    } finally {
      setExportLoading(false);
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

  if (loading) {
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
        {/* Navigation Breadcrumb & Back button */}
        <div className="flex items-center justify-between">
          <button
            onClick={clearSelection}
            className="inline-flex items-center gap-2 text-xs uppercase tracking-widest font-light text-muted-foreground hover:text-foreground transition"
          >
            <ArrowLeft className="w-4 h-4 text-[#9B8F77]" />
            <span>Back to Product Catalog</span>
          </button>

          <div className="flex items-center gap-3">
            <button
              onClick={() => handleExportCatalog('csv')}
              className="h-9 px-4 border border-border bg-card text-muted-foreground hover:text-foreground text-[10px] uppercase tracking-widest font-medium transition rounded-none inline-flex items-center gap-1.5"
            >
              <Download className="w-3.5 h-3.5 text-[#9B8F77]" />
              Export CSV
            </button>
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
            onResolutionCompleted={fetchProducts}
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

        <div className="flex items-center gap-3 self-start sm:self-auto">
          {/* Export Buttons */}
          <button
            onClick={() => handleExportCatalog('xlsx')}
            disabled={exportLoading || products.length === 0}
            className="h-10 px-4 border border-border bg-card text-muted-foreground hover:text-foreground text-[10px] uppercase tracking-widest font-medium transition duration-150 rounded-none inline-flex items-center gap-2 disabled:opacity-40"
          >
            <Download className="w-3.5 h-3.5 text-[#9B8F77]" />
            <span>Export Excel</span>
          </button>
          <button
            onClick={() => handleExportCatalog('csv')}
            disabled={exportLoading || products.length === 0}
            className="h-10 px-4 border border-border bg-card text-muted-foreground hover:text-foreground text-[10px] uppercase tracking-widest font-medium transition duration-150 rounded-none inline-flex items-center gap-2 disabled:opacity-40"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Export CSV</span>
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

        <div className="flex items-center gap-3">
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
