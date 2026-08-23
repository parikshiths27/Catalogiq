import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  LayoutDashboard,
  Database,
  UploadCloud,
  Activity,
  Search,
  CheckSquare,
  AlertTriangle,
  RefreshCw,
  FileText,
  Sparkles
} from 'lucide-react';
import { formatApiDateTime } from '../../lib/dates';
import { apiUrl } from '../../lib/api';

interface OverviewKpis {
  total_products: number;
  documents_processed: number;
  total_documents: number;
  active_processing_jobs: number;
  review_backlog: number;
  catalog_quality_score: number | null;
  verification_rate: number | null;
}

interface ProcessingActivityItem {
  id: string;
  filename: string;
  status: string;
  created_at: string;
  page_count: number | null;
  current_stage: string | null;
}

interface ReviewSummary {
  unresolved_validation_issues: number;
  conflicts_count: number;
  low_confidence_attributes: number;
  products_needing_review: number;
}

interface CatalogQualitySummary {
  overall_quality_score: number | null;
  completeness_rate: number | null;
  verified_products_count: number;
  needs_review_products_count: number;
  draft_products_count: number;
  evidence_coverage_rate: number | null;
  products_needing_attention: number;
}

interface RecentProductItem {
  id: string;
  product_name: string;
  brand: string;
  sku: string;
  category: string;
  status: string;
  quality_score: number;
  updated_at: string;
}

interface OverviewData {
  kpis: OverviewKpis;
  review_summary: ReviewSummary;
  catalog_quality_summary: CatalogQualitySummary;
  processing_activity: ProcessingActivityItem[];
  recent_products: RecentProductItem[];
}

interface DashboardErrorState {
  category: 'network' | 'http' | 'json' | 'schema' | 'unknown';
  categoryLabel: string;
  message: string;
  details?: string;
  statusCode?: number;
}

function normalizeOverviewData(raw: any): OverviewData {
  if (!raw || typeof raw !== 'object') {
    throw new Error('Expected JSON object in overview response');
  }

  const kpisRaw = raw.kpis || {};
  const reviewRaw = raw.review_summary || {};
  const qualityRaw = raw.catalog_quality_summary || {};

  const kpis: OverviewKpis = {
    total_products: typeof kpisRaw.total_products === 'number' ? kpisRaw.total_products : 0,
    documents_processed: typeof kpisRaw.documents_processed === 'number' ? kpisRaw.documents_processed : 0,
    total_documents: typeof kpisRaw.total_documents === 'number' ? kpisRaw.total_documents : 0,
    active_processing_jobs: typeof kpisRaw.active_processing_jobs === 'number' ? kpisRaw.active_processing_jobs : 0,
    review_backlog: typeof kpisRaw.review_backlog === 'number' ? kpisRaw.review_backlog : 0,
    catalog_quality_score: typeof kpisRaw.catalog_quality_score === 'number' ? kpisRaw.catalog_quality_score : null,
    verification_rate: typeof kpisRaw.verification_rate === 'number' ? kpisRaw.verification_rate : null,
  };

  const review_summary: ReviewSummary = {
    unresolved_validation_issues: typeof reviewRaw.unresolved_validation_issues === 'number' ? reviewRaw.unresolved_validation_issues : 0,
    conflicts_count: typeof reviewRaw.conflicts_count === 'number' ? reviewRaw.conflicts_count : 0,
    low_confidence_attributes: typeof reviewRaw.low_confidence_attributes === 'number' ? reviewRaw.low_confidence_attributes : 0,
    products_needing_review: typeof reviewRaw.products_needing_review === 'number' ? reviewRaw.products_needing_review : 0,
  };

  const catalog_quality_summary: CatalogQualitySummary = {
    overall_quality_score: typeof qualityRaw.overall_quality_score === 'number' ? qualityRaw.overall_quality_score : null,
    completeness_rate: typeof qualityRaw.completeness_rate === 'number' ? qualityRaw.completeness_rate : null,
    verified_products_count: typeof qualityRaw.verified_products_count === 'number' ? qualityRaw.verified_products_count : 0,
    needs_review_products_count: typeof qualityRaw.needs_review_products_count === 'number' ? qualityRaw.needs_review_products_count : 0,
    draft_products_count: typeof qualityRaw.draft_products_count === 'number' ? qualityRaw.draft_products_count : 0,
    evidence_coverage_rate: typeof qualityRaw.evidence_coverage_rate === 'number' ? qualityRaw.evidence_coverage_rate : null,
    products_needing_attention: typeof qualityRaw.products_needing_attention === 'number' ? qualityRaw.products_needing_attention : 0,
  };

  const processing_activity: ProcessingActivityItem[] = Array.isArray(raw.processing_activity)
    ? raw.processing_activity.map((item: any) => ({
        id: String(item?.id || ''),
        filename: String(item?.filename || 'Untitled document'),
        status: String(item?.status || 'unknown'),
        created_at: String(item?.created_at || ''),
        page_count: typeof item?.page_count === 'number' ? item.page_count : null,
        current_stage: item?.current_stage ? String(item.current_stage) : null,
      }))
    : [];

  const recent_products: RecentProductItem[] = Array.isArray(raw.recent_products)
    ? raw.recent_products.map((item: any) => ({
        id: String(item?.id || ''),
        product_name: String(item?.product_name || 'Unnamed Product'),
        brand: String(item?.brand || '-'),
        sku: String(item?.sku || '-'),
        category: String(item?.category || '-'),
        status: String(item?.status || 'draft'),
        quality_score: typeof item?.quality_score === 'number' ? item.quality_score : 0,
        updated_at: String(item?.updated_at || ''),
      }))
    : [];

  return {
    kpis,
    review_summary,
    catalog_quality_summary,
    processing_activity,
    recent_products,
  };
}

export const DashboardShell: React.FC = () => {
  const navigate = useNavigate();

  const {
    data,
    isLoading: loading,
    error,
    refetch,
    isFetching,
  } = useQuery<OverviewData, DashboardErrorState>({
    queryKey: ['overview-summary'],
    queryFn: async () => {
      let res: Response;
      const url = apiUrl('/api/v1/overview/summary');

      // 1. Network / Request Execution
      try {
        res = await fetch(url);
      } catch (networkErr: any) {
        console.error('[Overview Dashboard] Network error during fetch:', {
          url,
          error: networkErr,
        });
        throw {
          category: 'network',
          categoryLabel: 'Network / Connection Error',
          message: 'Could not connect to backend server. Please verify your internet connection or backend availability.',
          details: networkErr?.message || String(networkErr),
        } as DashboardErrorState;
      }

      // 2. HTTP Status Check
      if (!res.ok) {
        let errorBody = '';
        try {
          errorBody = await res.text();
        } catch {
          // ignore text read failure
        }
        console.error('[Overview Dashboard] HTTP error response:', {
          status: res.status,
          statusText: res.statusText,
          url,
          body: errorBody,
        });
        throw {
          category: 'http',
          categoryLabel: `HTTP Error (${res.status})`,
          message: `Backend service returned error status ${res.status} (${res.statusText}).`,
          details: errorBody ? errorBody.slice(0, 300) : undefined,
          statusCode: res.status,
        } as DashboardErrorState;
      }

      // 3. JSON Parsing Check
      let rawJson: any = null;
      try {
        rawJson = await res.json();
      } catch (jsonErr: any) {
        console.error('[Overview Dashboard] JSON parsing error on HTTP 200 response:', {
          url,
          error: jsonErr,
        });
        throw {
          category: 'json',
          categoryLabel: 'JSON Parse Error',
          message: 'Server returned HTTP 200, but response body was not valid JSON.',
          details: jsonErr?.message || String(jsonErr),
        } as DashboardErrorState;
      }

      // 4. Response Schema & Data Normalization
      try {
        return normalizeOverviewData(rawJson);
      } catch (schemaErr: any) {
        console.error('[Overview Dashboard] Response schema mismatch:', {
          url,
          rawJson,
          error: schemaErr,
        });
        throw {
          category: 'schema',
          categoryLabel: 'Response Schema Error',
          message: 'Overview data structure returned by backend is missing required fields.',
          details: schemaErr?.message || String(schemaErr),
        } as DashboardErrorState;
      }
    },
    staleTime: 30000,
  });

  if (loading) {
    return (
      <div className="space-y-6 text-foreground animate-pulse">
        <div className="flex items-center justify-between">
          <div className="space-y-2">
            <div className="h-8 w-48 bg-card border border-border"></div>
            <div className="h-4 w-96 bg-card/60"></div>
          </div>
          <div className="h-9 w-24 bg-card border border-border"></div>
        </div>

        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="p-5 bg-card border border-border space-y-3">
              <div className="h-3 w-24 bg-border"></div>
              <div className="h-8 w-16 bg-border"></div>
              <div className="h-3 w-28 bg-border/60"></div>
            </div>
          ))}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="h-64 bg-card border border-border"></div>
          <div className="h-64 bg-card border border-border"></div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6 text-foreground">
        <div className="flex items-center gap-3">
          <LayoutDashboard className="w-8 h-8 text-muted-foreground" />
          <div>
            <h2 className="text-3xl font-serif font-normal tracking-tight">Overview</h2>
            <p className="text-xs uppercase tracking-wider text-muted-foreground">Operational CatalogIQ dashboard</p>
          </div>
        </div>
        <div className="p-8 bg-destructive/10 border border-destructive/30 flex flex-col items-center justify-center text-center space-y-4">
          <AlertTriangle className="w-12 h-12 text-destructive" />
          <div className="max-w-md space-y-2">
            <span className="inline-block px-2.5 py-0.5 text-[9px] uppercase tracking-widest font-mono font-semibold bg-destructive/20 text-destructive border border-destructive/40">
              {error.categoryLabel}
            </span>
            <h3 className="font-semibold text-lg text-foreground font-serif">Unable to Load Overview Summary</h3>
            <p className="text-xs text-muted-foreground">{error.message}</p>
            {error.details && (
              <p className="text-[11px] font-mono text-muted-foreground/80 bg-background/50 p-2 border border-border mt-2 break-all text-left">
                {error.details}
              </p>
            )}
          </div>
          <button
            onClick={() => refetch()}
            className="px-4 py-2 bg-destructive text-destructive-foreground hover:opacity-90 font-medium text-xs uppercase tracking-widest flex items-center gap-2 border border-destructive transition"
          >
            <RefreshCw className="w-4 h-4" /> Retry
          </button>
        </div>
      </div>
    );
  }

  const kpis = data?.kpis;
  const reviewSummary = data?.review_summary;
  const activity = data?.processing_activity || [];
  const recentProducts = data?.recent_products || [];

  const hasProducts = (kpis?.total_products ?? 0) > 0;

  const primaryActions = [
    { label: 'Upload Source', icon: UploadCloud, to: '/upload', primary: true },
    { label: 'Review Issues', icon: CheckSquare, to: '/reviews' },
    { label: 'Search Catalog', icon: Search, to: '/search' },
  ];

  // Only show KPI cards with real, meaningful data
  const kpiCards = [
    {
      label: 'Total Products',
      value: kpis?.total_products ?? 0,
      detail: 'Products in catalog',
      icon: Database,
      accent: 'text-[#9B8F77]',
    },
    {
      label: 'Sources Processed',
      value: kpis?.documents_processed ?? 0,
      detail: `${kpis?.total_documents ?? 0} total documents uploaded`,
      icon: FileText,
      accent: 'text-foreground',
    },
    {
      label: 'Active Jobs',
      value: kpis?.active_processing_jobs ?? 0,
      detail: (kpis?.active_processing_jobs ?? 0) > 0 ? 'Processing pipeline active' : 'No active queue',
      icon: Activity,
      accent: 'text-[#9B8F77]',
    },
    {
      label: 'Review Backlog',
      value: kpis?.review_backlog ?? 0,
      detail: `${reviewSummary?.products_needing_review ?? 0} products need review`,
      icon: CheckSquare,
      accent: 'text-amber-500',
    },
  ];

  return (
    <div className="space-y-8 text-foreground rounded-none">
      {/* Hero Section */}
      <section className="border border-border bg-card p-8 rounded-none relative overflow-hidden">
        <div className="absolute right-0 top-0 w-1/3 h-full opacity-[0.03] pointer-events-none mesh-grid border-l border-border" />
        
        <div className="flex flex-col gap-8 z-10 relative">
          <div className="space-y-6">
            <div className="inline-flex items-center gap-2 border border-[#9B8F77]/30 bg-[#9B8F77]/5 px-3 py-1.5 text-[9px] uppercase tracking-widest font-medium text-[#9B8F77]">
              <Sparkles className="w-3.5 h-3.5" />
              Product Intelligence Engine
            </div>
            <div className="max-w-3xl space-y-4">
              <h2 className="text-foreground text-4xl lg:text-5xl font-normal leading-tight font-serif">
                Product data that explains itself.
              </h2>
              <p className="text-xs uppercase tracking-wider text-muted-foreground leading-relaxed max-w-xl font-light">
                CatalogIQ transforms raw industrial specifications into structured attribute claims, confidence scores, evidence provenance, and verified catalog intelligence.
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {primaryActions.map((action) => {
              const Icon = action.icon;
              return (
                <button
                  key={action.label}
                  onClick={() => navigate(action.to)}
                  className={`h-10 px-5 text-xs uppercase tracking-widest font-medium transition duration-150 rounded-none border ${
                    action.primary
                      ? 'bg-foreground text-background border-foreground hover:bg-transparent hover:text-foreground'
                      : 'border-border bg-background text-muted-foreground hover:bg-card hover:text-foreground'
                  }`}
                >
                  <Icon className="w-3.5 h-3.5 mr-2 inline" />
                  {action.label}
                </button>
              );
            })}
            <button
              onClick={() => refetch()}
              className="h-10 border border-border bg-background px-5 text-xs uppercase tracking-widest font-medium text-muted-foreground hover:text-foreground hover:bg-card transition flex items-center gap-2"
            >
              <RefreshCw className={`w-3.5 h-3.5 text-[#9B8F77] ${isFetching ? 'animate-spin' : ''}`} /> Refresh
            </button>
          </div>
        </div>
      </section>

      {/* KPI Cards Grid */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {kpiCards.map((card) => {
          const Icon = card.icon;
          return (
            <div
              key={card.label}
              className="p-5 border border-border bg-card hover:bg-accent/40 transition duration-150 rounded-none space-y-3 relative select-none"
            >
              <div className="flex items-center justify-between text-muted-foreground">
                <span className="text-[10px] font-light tracking-widest uppercase">{card.label}</span>
                <Icon className={`w-4 h-4 ${card.accent}`} />
              </div>
              <div className="text-3xl font-serif font-normal tracking-tight text-foreground">
                {card.value}
              </div>
              <p className="text-[10px] font-light uppercase tracking-wider text-muted-foreground">
                {card.detail}
              </p>
            </div>
          );
        })}
      </div>

      {/* Empty State when no products */}
      {!hasProducts && (
        <div className="p-12 border border-border bg-card text-center space-y-4 rounded-none">
          <Database className="w-12 h-12 text-muted-foreground opacity-50 mx-auto" />
          <h3 className="font-serif text-xl font-normal text-foreground">No Products in Catalog Yet</h3>
          <p className="text-xs uppercase tracking-wider text-muted-foreground font-light max-w-md mx-auto">
            Upload a document (PDF, Excel, CSV, or other formats) to start extracting, enriching, and validating your product catalog.
          </p>
          <button
            onClick={() => navigate('/upload')}
            className="h-10 px-6 bg-foreground text-background border border-foreground hover:bg-transparent hover:text-foreground text-[10px] uppercase tracking-widest font-semibold transition duration-150 rounded-none inline-flex items-center gap-2"
          >
            <UploadCloud className="w-3.5 h-3.5" />
            <span>Upload Your First Document</span>
          </button>
        </div>
      )}

      {/* Recent Enriched Products & Ingestion Activity */}
      {hasProducts && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Recent Products */}
          <div className="border border-border bg-card p-6 space-y-4 rounded-none">
            <div className="flex items-center justify-between border-b border-border pb-4">
              <h3 className="font-serif text-xl font-normal text-foreground flex items-center gap-2">
                <Database className="w-4 h-4 text-[#9B8F77]" />
                <span>Recently Enriched Products</span>
              </h3>
              <button
                onClick={() => navigate('/catalog')}
                className="text-[10px] uppercase tracking-widest text-[#9B8F77] hover:text-foreground font-semibold"
              >
                View All &rarr;
              </button>
            </div>

            {recentProducts.length === 0 ? (
              <div className="py-12 text-center text-xs text-muted-foreground space-y-2 font-light uppercase tracking-wider">
                <Database className="w-8 h-8 mx-auto text-muted-foreground opacity-50" />
                <p>No products in catalog yet.</p>
              </div>
            ) : (
              <div className="divide-y divide-border">
                {recentProducts.slice(0, 5).map((prod) => (
                  <div
                    key={prod.id}
                    onClick={() => navigate(`/catalog?product_id=${prod.id}`)}
                    className="py-3 flex items-center justify-between gap-4 hover:bg-accent/40 px-2 cursor-pointer transition"
                  >
                    <div className="min-w-0 space-y-0.5">
                      <div className="text-xs font-medium text-foreground truncate">{prod.product_name}</div>
                      <div className="flex items-center gap-2 text-[10px] text-muted-foreground uppercase font-mono tracking-wider">
                        <span>{prod.sku}</span>
                        <span>•</span>
                        <span>{prod.brand}</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <span className="text-[10px] font-mono px-2 py-0.5 border border-border bg-background">
                        {Math.round(Number(prod.quality_score) || 0)}%
                      </span>
                      <span className="text-[9px] uppercase tracking-widest px-2 py-0.5 border border-border bg-accent text-foreground">
                        {prod.status}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Ingestion Activity Stream */}
          <div className="border border-border bg-card p-6 space-y-4 rounded-none">
            <div className="flex items-center justify-between border-b border-border pb-4">
              <h3 className="font-serif text-xl font-normal text-foreground flex items-center gap-2">
                <Activity className="w-4 h-4 text-[#9B8F77]" />
                <span>Recent Ingestion Activity</span>
              </h3>
              <button
                onClick={() => navigate('/upload')}
                className="text-[10px] uppercase tracking-widest text-[#9B8F77] hover:text-foreground font-semibold"
              >
                Batch Upload &rarr;
              </button>
            </div>

            {activity.length === 0 ? (
              <div className="py-12 text-center text-xs text-muted-foreground space-y-2 font-light uppercase tracking-wider">
                <FileText className="w-8 h-8 mx-auto text-muted-foreground opacity-50" />
                <p>No recent activity.</p>
              </div>
            ) : (
              <div className="divide-y divide-border">
                {activity.slice(0, 5).map((doc) => (
                  <div key={doc.id} className="py-3 flex items-center justify-between gap-4 px-2">
                    <div className="min-w-0 space-y-0.5">
                      <div className="text-xs font-medium text-foreground truncate">{doc.filename}</div>
                      <div className="flex items-center gap-2 text-[10px] text-muted-foreground font-mono">
                        <span>{doc.created_at ? formatApiDateTime(doc.created_at) : '-'}</span>
                        {doc.page_count && <span>• {doc.page_count} pages</span>}
                      </div>
                    </div>
                    <span className="text-[9px] uppercase tracking-widest px-2 py-0.5 border border-border bg-accent text-foreground">
                      {doc.status}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
