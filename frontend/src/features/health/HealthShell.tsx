import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  HeartPulse,
  Activity,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  Layers,
  ShieldCheck,
  FileText,
  UploadCloud,
  ChevronRight,
  TrendingUp
} from 'lucide-react';
import { ConfidenceBadge } from '../../components/ui/ConfidenceBadge';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { apiUrl } from '../../lib/api';

export interface OverallHealth {
  quality_score: number;
  completeness_rate: number;
  verification_rate: number;
  evidence_coverage: number;
  total_products: number;
  total_attributes: number;
  total_documents: number;
}

export interface StatusBreakdown {
  verified: number;
  needs_review: number;
  draft: number;
}

export interface IssuesSummary {
  total_open_issues: number;
  cross_source_conflicts: number;
  low_confidence_attributes: number;
  validation_issues: number;
  missing_required_attributes: number;
}

export interface CategoryHealthItem {
  category: string;
  product_count: number;
  avg_quality_score: number;
  verification_rate: number;
  completeness_rate: number;
  open_issues_count: number;
  conflicts_count: number;
}

export interface BrandHealthItem {
  brand: string;
  product_count: number;
  avg_quality_score: number;
  verification_rate: number;
  completeness_rate: number;
  open_issues_count: number;
  conflicts_count: number;
}

export interface ProductAttentionItem {
  id: string;
  product_name: string;
  brand: string;
  sku: string;
  category: string;
  status: string;
  quality_score: number;
  open_issues_count: number;
  has_conflicts: boolean;
  missing_required_count: number;
  updated_at: string;
}

export interface CatalogHealthResponse {
  overall: OverallHealth;
  status_breakdown: StatusBreakdown;
  issues: IssuesSummary;
  category_health: CategoryHealthItem[];
  brand_health: BrandHealthItem[];
  products_needing_attention: ProductAttentionItem[];
  worst_products: ProductAttentionItem[];
}

export const HealthShell: React.FC = () => {
  const [catSortField, setCatSortField] = useState<'product_count' | 'avg_quality_score' | 'verification_rate' | 'open_issues_count'>('product_count');
  const [catSortDir, setCatSortDir] = useState<'asc' | 'desc'>('desc');

  const [brandSortField, setBrandSortField] = useState<'product_count' | 'avg_quality_score' | 'verification_rate' | 'open_issues_count'>('product_count');
  const [brandSortDir, setBrandSortDir] = useState<'asc' | 'desc'>('desc');

  const { data, isLoading, isError, error, refetch, isRefetching } = useQuery<CatalogHealthResponse>({
    queryKey: ['catalogHealth'],
    queryFn: async () => {
      const res = await fetch(apiUrl('/api/v1/health/catalog'));
      if (!res.ok) {
        throw new Error(`Failed to fetch catalog health: ${res.statusText}`);
      }
      return res.json();
    },
  });

  if (isLoading) {
    return (
      <div className="space-y-6 text-foreground animate-pulse rounded-none">
        <div className="flex items-center justify-between">
          <div className="space-y-2">
            <div className="h-8 w-48 bg-card border border-border"></div>
            <div className="h-4 w-96 bg-card/60"></div>
          </div>
          <div className="h-9 w-24 bg-card border border-border"></div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-4">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="p-4 bg-card border border-border h-24"></div>
          ))}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="p-5 bg-card border border-border h-64"></div>
          <div className="p-5 bg-card border border-border h-64 lg:col-span-2"></div>
        </div>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="space-y-6 text-foreground rounded-none">
        <div className="p-8 bg-card border border-destructive/30 text-center space-y-4 rounded-none">
          <AlertTriangle className="w-12 h-12 text-destructive mx-auto" />
          <h3 className="text-xl font-serif font-normal text-foreground">Catalog Health Data Unavailable</h3>
          <p className="text-xs text-muted-foreground max-w-md mx-auto font-light">
            {error instanceof Error ? error.message : 'An error occurred while loading catalog health summary.'}
          </p>
          <button
            onClick={() => refetch()}
            className="px-5 py-2.5 bg-foreground text-background border border-foreground hover:bg-transparent hover:text-foreground text-[10px] uppercase tracking-widest font-semibold transition inline-flex items-center gap-2 rounded-none"
          >
            <RefreshCw className="w-3.5 h-3.5" /> Retry Fetch
          </button>
        </div>
      </div>
    );
  }

  const { overall, status_breakdown, issues, category_health, brand_health, products_needing_attention, worst_products } = data;

  if (overall.total_products === 0) {
    return (
      <div className="space-y-8 text-foreground rounded-none">
        <div className="flex items-center justify-between border-b border-border pb-4">
          <div className="space-y-1">
            <div className="inline-flex items-center gap-2 border border-[#9B8F77]/30 bg-[#9B8F77]/5 px-3 py-1 text-[9px] uppercase tracking-widest font-medium text-[#9B8F77] mb-2">
              <HeartPulse className="w-3.5 h-3.5" />
              Health Analytics Engine
            </div>
            <h1 className="text-3xl lg:text-4xl font-serif font-normal text-foreground tracking-tight">
              Catalog Health & Quality Metrics
            </h1>
            <p className="text-xs uppercase tracking-wider text-muted-foreground font-light">
              Understand catalog quality, completeness, evidence coverage, and review risk.
            </p>
          </div>
        </div>

        <div className="p-12 border border-border bg-card text-center space-y-5 rounded-none">
          <Activity className="w-12 h-12 text-muted-foreground opacity-50 mx-auto" />
          <div>
            <h3 className="text-xl font-serif font-normal text-foreground">Catalog is Empty</h3>
            <p className="text-xs uppercase tracking-wider text-muted-foreground mt-1 max-w-md mx-auto font-light">
              Upload a catalog document (PDF, Excel, CSV) to begin extracting specifications and tracking real-time data health.
            </p>
          </div>
          <div className="flex items-center justify-center gap-3 pt-2">
            <Link
              to="/upload"
              className="h-10 px-6 bg-foreground text-background border border-foreground hover:bg-transparent hover:text-foreground text-[10px] uppercase tracking-widest font-semibold transition duration-150 rounded-none inline-flex items-center gap-2"
            >
              <UploadCloud className="w-3.5 h-3.5" /> Upload Document
            </Link>
          </div>
        </div>
      </div>
    );
  }

  // Sorted Category Health
  const sortedCategories = [...category_health].sort((a, b) => {
    const valA = a[catSortField];
    const valB = b[catSortField];
    return catSortDir === 'asc' ? (valA > valB ? 1 : -1) : (valA < valB ? 1 : -1);
  });

  // Sorted Brand Health
  const sortedBrands = [...brand_health].sort((a, b) => {
    const valA = a[brandSortField];
    const valB = b[brandSortField];
    return brandSortDir === 'asc' ? (valA > valB ? 1 : -1) : (valA < valB ? 1 : -1);
  });

  const toggleCatSort = (field: 'product_count' | 'avg_quality_score' | 'verification_rate' | 'open_issues_count') => {
    if (catSortField === field) {
      setCatSortDir(catSortDir === 'asc' ? 'desc' : 'asc');
    } else {
      setCatSortField(field);
      setCatSortDir('desc');
    }
  };

  const toggleBrandSort = (field: 'product_count' | 'avg_quality_score' | 'verification_rate' | 'open_issues_count') => {
    if (brandSortField === field) {
      setBrandSortDir(brandSortDir === 'asc' ? 'desc' : 'asc');
    } else {
      setBrandSortField(field);
      setBrandSortDir('desc');
    }
  };

  return (
    <div className="space-y-8 text-foreground rounded-none">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="space-y-1">
          <div className="inline-flex items-center gap-2 border border-[#9B8F77]/30 bg-[#9B8F77]/5 px-3 py-1 text-[9px] uppercase tracking-widest font-medium text-[#9B8F77] mb-2">
            <HeartPulse className="w-3.5 h-3.5" />
            Health Analytics Engine
          </div>
          <h1 className="text-3xl lg:text-4xl font-serif font-normal text-foreground tracking-tight">
            Catalog Health & Quality Metrics
          </h1>
          <p className="text-xs uppercase tracking-wider text-muted-foreground font-light">
            Comprehensive health metrics computed across all {overall.total_products} items in your master catalog.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => refetch()}
            disabled={isRefetching}
            className="h-10 px-4 border border-border bg-card text-muted-foreground hover:text-foreground text-xs uppercase tracking-widest font-medium transition rounded-none flex items-center gap-2 disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-[#9B8F77] ${isRefetching ? 'animate-spin' : ''}`} /> Refresh
          </button>
        </div>
      </div>

      {overall.total_products === 0 ? (
        <div className="p-12 border border-border bg-card text-center space-y-4 rounded-none">
          <HeartPulse className="w-12 h-12 text-muted-foreground opacity-50 mx-auto" />
          <h3 className="font-serif text-xl font-normal text-foreground">No Catalog Health Data</h3>
          <p className="text-xs uppercase tracking-wider text-muted-foreground font-light max-w-md mx-auto">
            Ingest and enrich catalog documentation to view automated quality scores, completeness breakdowns, and category health analytics.
          </p>
          <Link
            to="/upload"
            className="h-10 px-6 bg-foreground text-background border border-foreground hover:bg-transparent hover:text-foreground text-[10px] uppercase tracking-widest font-semibold transition duration-150 rounded-none inline-flex items-center gap-2"
          >
            <UploadCloud className="w-3.5 h-3.5" />
            <span>Upload Catalog Documents</span>
          </Link>
        </div>
      ) : (
        <>
          {/* Top 6 KPI Cards with Clear Explanations */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-4">
        {/* 1. Catalog Quality */}
        <div className="p-5 border border-border bg-card rounded-none space-y-2 relative group">
          <div className="flex items-center justify-between text-muted-foreground">
            <span className="text-[10px] font-light tracking-widest uppercase">Catalog Quality</span>
            <Activity className="w-4 h-4 text-emerald-500" />
          </div>
          <div className="text-3xl font-serif font-normal text-emerald-500">
            {overall.quality_score.toFixed(1)}%
          </div>
          <p className="text-[10px] text-muted-foreground font-light leading-snug">
            Avg quality score across all items based on completeness and evidence.
          </p>
        </div>

        {/* 2. Completeness Rate */}
        <div className="p-5 border border-border bg-card rounded-none space-y-2 relative group">
          <div className="flex items-center justify-between text-muted-foreground">
            <span className="text-[10px] font-light tracking-widest uppercase">Completeness</span>
            <Layers className="w-4 h-4 text-foreground" />
          </div>
          <div className="text-3xl font-serif font-normal text-foreground">
            {overall.completeness_rate.toFixed(1)}%
          </div>
          <p className="text-[10px] text-muted-foreground font-light leading-snug">
            Required and optional attributes extracted from sources.
          </p>
        </div>

        {/* 3. Verification Rate */}
        <div className="p-5 border border-border bg-card rounded-none space-y-2 relative group">
          <div className="flex items-center justify-between text-muted-foreground">
            <span className="text-[10px] font-light tracking-widest uppercase">Verification</span>
            <CheckCircle2 className="w-4 h-4 text-[#9B8F77]" />
          </div>
          <div className="text-3xl font-serif font-normal text-[#9B8F77]">
            {overall.verification_rate.toFixed(1)}%
          </div>
          <p className="text-[10px] text-muted-foreground font-light leading-snug">
            {status_breakdown.verified} of {overall.total_products} products verified.
          </p>
        </div>

        {/* 4. Evidence Coverage */}
        <div className="p-5 border border-border bg-card rounded-none space-y-2 relative group">
          <div className="flex items-center justify-between text-muted-foreground">
            <span className="text-[10px] font-light tracking-widest uppercase">Evidence Cov.</span>
            <ShieldCheck className="w-4 h-4 text-foreground" />
          </div>
          <div className="text-3xl font-serif font-normal text-foreground">
            {overall.evidence_coverage.toFixed(1)}%
          </div>
          <p className="text-[10px] text-muted-foreground font-light leading-snug">
            Specs grounded in verbatim document text.
          </p>
        </div>

        {/* 5. Open Reviews */}
        <Link
          to="/reviews"
          className="p-5 border border-border bg-card hover:border-amber-500/60 rounded-none space-y-2 transition block"
        >
          <div className="flex items-center justify-between text-muted-foreground">
            <span className="text-[10px] font-light tracking-widest uppercase">Open Reviews</span>
            <AlertTriangle className="w-4 h-4 text-amber-500" />
          </div>
          <div className="text-3xl font-serif font-normal text-amber-500">
            {issues.total_open_issues}
          </div>
          <p className="text-[10px] text-[#9B8F77] font-light group-hover:text-foreground transition">
            Inspect review queue &rarr;
          </p>
        </Link>

        {/* 6. Conflicts */}
        <Link
          to="/reviews?issue_type=cross_source_conflict"
          className="p-5 border border-border bg-card hover:border-destructive/60 rounded-none space-y-2 transition block"
        >
          <div className="flex items-center justify-between text-muted-foreground">
            <span className="text-[10px] font-light tracking-widest uppercase">Conflicts</span>
            <TrendingUp className="w-4 h-4 text-destructive" />
          </div>
          <div className="text-3xl font-serif font-normal text-destructive">
            {issues.cross_source_conflicts}
          </div>
          <p className="text-[10px] text-destructive font-light transition">
            Resolve conflicts &rarr;
          </p>
        </Link>
      </div>

      {/* Section: Status Breakdown & Issue Cards Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Status Distribution */}
        <div className="p-6 border border-border bg-card space-y-5 rounded-none">
          <div className="flex items-center justify-between border-b border-border pb-3">
            <h3 className="text-xs font-medium uppercase tracking-widest text-[#9B8F77]">
              Product Status Breakdown
            </h3>
            <span className="text-[10px] font-mono text-muted-foreground">Total: {overall.total_products}</span>
          </div>

          {/* Stacked Progress Bar */}
          <div className="h-3 w-full bg-background border border-border rounded-none overflow-hidden flex">
            <div
              style={{ width: `${(status_breakdown.verified / overall.total_products) * 100}%` }}
              className="bg-emerald-500 h-full"
              title={`Verified: ${status_breakdown.verified}`}
            />
            <div
              style={{ width: `${(status_breakdown.needs_review / overall.total_products) * 100}%` }}
              className="bg-amber-500 h-full"
              title={`Needs Review: ${status_breakdown.needs_review}`}
            />
            <div
              style={{ width: `${(status_breakdown.draft / overall.total_products) * 100}%` }}
              className="bg-muted-foreground/30 h-full"
              title={`Draft: ${status_breakdown.draft}`}
            />
          </div>

          <div className="space-y-3 pt-2 text-xs">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 bg-emerald-500"></span>
                <span>Verified</span>
              </div>
              <div className="font-mono font-medium">
                {status_breakdown.verified} <span className="text-muted-foreground font-normal">({((status_breakdown.verified / overall.total_products) * 100).toFixed(1)}%)</span>
              </div>
            </div>

            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 bg-amber-500"></span>
                <span>Needs Review</span>
              </div>
              <div className="font-mono font-medium">
                {status_breakdown.needs_review} <span className="text-muted-foreground font-normal">({((status_breakdown.needs_review / overall.total_products) * 100).toFixed(1)}%)</span>
              </div>
            </div>

            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 bg-muted-foreground/40"></span>
                <span>Draft</span>
              </div>
              <div className="font-mono font-medium">
                {status_breakdown.draft} <span className="text-muted-foreground font-normal">({((status_breakdown.draft / overall.total_products) * 100).toFixed(1)}%)</span>
              </div>
            </div>
          </div>
        </div>

        {/* Issue Category Cards Grid */}
        <div className="lg:col-span-2 grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Link
            to="/reviews"
            className="p-5 border border-border bg-card hover:border-foreground/40 transition rounded-none flex flex-col justify-between space-y-3"
          >
            <div>
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-medium uppercase tracking-widest text-[#9B8F77]">Open Reviews</span>
                <AlertTriangle className="w-4 h-4 text-amber-500" />
              </div>
              <div className="text-3xl font-serif font-normal text-foreground mt-2">{issues.total_open_issues}</div>
              <p className="text-xs text-muted-foreground mt-1 font-light">Validation rules requiring approval or correction.</p>
            </div>
            <div className="text-[10px] uppercase tracking-widest text-[#9B8F77] flex items-center gap-1 font-medium pt-2">
              Filter review queue <ChevronRight className="w-3 h-3" />
            </div>
          </Link>

          <Link
            to="/reviews?issue_type=cross_source_conflict"
            className="p-5 border border-border bg-card hover:border-destructive/60 transition rounded-none flex flex-col justify-between space-y-3"
          >
            <div>
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-medium uppercase tracking-widest text-destructive">Multi-Source Conflicts</span>
                <TrendingUp className="w-4 h-4 text-destructive" />
              </div>
              <div className="text-3xl font-serif font-normal text-destructive mt-2">{issues.cross_source_conflicts}</div>
              <p className="text-xs text-muted-foreground mt-1 font-light">Inconsistent specifications extracted across sources.</p>
            </div>
            <div className="text-[10px] uppercase tracking-widest text-destructive flex items-center gap-1 font-medium pt-2">
              Filter conflicts <ChevronRight className="w-3 h-3" />
            </div>
          </Link>

          <Link
            to="/reviews?issue_type=low_confidence"
            className="p-5 border border-border bg-card hover:border-amber-500/60 transition rounded-none flex flex-col justify-between space-y-3"
          >
            <div>
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-medium uppercase tracking-widest text-amber-500">Low Confidence Fields</span>
                <ShieldCheck className="w-4 h-4 text-amber-500" />
              </div>
              <div className="text-3xl font-serif font-normal text-amber-500 mt-2">{issues.low_confidence_attributes}</div>
              <p className="text-xs text-muted-foreground mt-1 font-light">Extraction confidence below 75% requiring human verification.</p>
            </div>
            <div className="text-[10px] uppercase tracking-widest text-amber-500 flex items-center gap-1 font-medium pt-2">
              Filter low confidence <ChevronRight className="w-3 h-3" />
            </div>
          </Link>

          <Link
            to="/reviews?issue_type=missing_attribute"
            className="p-5 border border-border bg-card hover:border-foreground/40 transition rounded-none flex flex-col justify-between space-y-3"
          >
            <div>
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-medium uppercase tracking-widest text-[#9B8F77]">Missing Required Specs</span>
                <FileText className="w-4 h-4 text-foreground" />
              </div>
              <div className="text-3xl font-serif font-normal text-foreground mt-2">{issues.missing_required_attributes}</div>
              <p className="text-xs text-muted-foreground mt-1 font-light">Category-specific mandatory attributes missing from extraction.</p>
            </div>
            <div className="text-[10px] uppercase tracking-widest text-[#9B8F77] flex items-center gap-1 font-medium pt-2">
              Filter missing fields <ChevronRight className="w-3 h-3" />
            </div>
          </Link>
        </div>
      </div>

      {/* Category & Brand Health Tables */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Category Health */}
        <div className="p-6 border border-border bg-card space-y-4 rounded-none">
          <div className="flex items-center justify-between border-b border-border pb-3">
            <h3 className="font-serif text-xl font-normal text-foreground">
              Category Quality Health
            </h3>
            <span className="text-[10px] font-mono text-muted-foreground">{category_health.length} categories</span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-border text-[9px] uppercase tracking-widest text-muted-foreground font-medium">
                  <th className="py-2.5 px-2">Category</th>
                  <th
                    className="py-2.5 px-2 cursor-pointer hover:text-foreground"
                    onClick={() => toggleCatSort('product_count')}
                  >
                    Products {catSortField === 'product_count' ? (catSortDir === 'asc' ? '↑' : '↓') : ''}
                  </th>
                  <th
                    className="py-2.5 px-2 cursor-pointer hover:text-foreground"
                    onClick={() => toggleCatSort('avg_quality_score')}
                  >
                    Avg Quality {catSortField === 'avg_quality_score' ? (catSortDir === 'asc' ? '↑' : '↓') : ''}
                  </th>
                  <th
                    className="py-2.5 px-2 cursor-pointer hover:text-foreground"
                    onClick={() => toggleCatSort('verification_rate')}
                  >
                    Verified % {catSortField === 'verification_rate' ? (catSortDir === 'asc' ? '↑' : '↓') : ''}
                  </th>
                  <th className="py-2.5 px-2 text-right">Issues</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {sortedCategories.map((c) => (
                  <tr key={c.category} className="hover:bg-accent/40 transition">
                    <td className="py-3 px-2 font-medium text-foreground">{c.category}</td>
                    <td className="py-3 px-2 text-muted-foreground font-mono">{c.product_count}</td>
                    <td className="py-3 px-2">
                      <ConfidenceBadge confidence={c.avg_quality_score} size="sm" />
                    </td>
                    <td className="py-3 px-2 font-mono text-muted-foreground">{c.verification_rate.toFixed(1)}%</td>
                    <td className="py-3 px-2 text-right font-mono">
                      {c.open_issues_count > 0 ? (
                        <span className="text-amber-500 font-semibold">{c.open_issues_count} open</span>
                      ) : (
                        <span className="text-emerald-500">0</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Brand Health */}
        <div className="p-6 border border-border bg-card space-y-4 rounded-none">
          <div className="flex items-center justify-between border-b border-border pb-3">
            <h3 className="font-serif text-xl font-normal text-foreground">
              Brand Quality Health
            </h3>
            <span className="text-[10px] font-mono text-muted-foreground">{brand_health.length} brands</span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-border text-[9px] uppercase tracking-widest text-muted-foreground font-medium">
                  <th className="py-2.5 px-2">Brand</th>
                  <th
                    className="py-2.5 px-2 cursor-pointer hover:text-foreground"
                    onClick={() => toggleBrandSort('product_count')}
                  >
                    Products {brandSortField === 'product_count' ? (brandSortDir === 'asc' ? '↑' : '↓') : ''}
                  </th>
                  <th
                    className="py-2.5 px-2 cursor-pointer hover:text-foreground"
                    onClick={() => toggleBrandSort('avg_quality_score')}
                  >
                    Avg Quality {brandSortField === 'avg_quality_score' ? (brandSortDir === 'asc' ? '↑' : '↓') : ''}
                  </th>
                  <th
                    className="py-2.5 px-2 cursor-pointer hover:text-foreground"
                    onClick={() => toggleBrandSort('verification_rate')}
                  >
                    Verified % {brandSortField === 'verification_rate' ? (brandSortDir === 'asc' ? '↑' : '↓') : ''}
                  </th>
                  <th className="py-2.5 px-2 text-right">Issues</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {sortedBrands.map((b) => (
                  <tr key={b.brand} className="hover:bg-accent/40 transition">
                    <td className="py-3 px-2 font-medium text-foreground">{b.brand}</td>
                    <td className="py-3 px-2 text-muted-foreground font-mono">{b.product_count}</td>
                    <td className="py-3 px-2">
                      <ConfidenceBadge confidence={b.avg_quality_score} size="sm" />
                    </td>
                    <td className="py-3 px-2 font-mono text-muted-foreground">{b.verification_rate.toFixed(1)}%</td>
                    <td className="py-3 px-2 text-right font-mono">
                      {b.open_issues_count > 0 ? (
                        <span className="text-amber-500 font-semibold">{b.open_issues_count} open</span>
                      ) : (
                        <span className="text-emerald-500">0</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Attention Queue: Products Needing Attention */}
      <div className="p-6 border border-border bg-card space-y-4 rounded-none">
        <div className="flex items-center justify-between border-b border-border pb-3">
          <div>
            <h3 className="font-serif text-xl font-normal text-foreground flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-500" />
              <span>Products Needing Attention</span>
            </h3>
            <p className="text-xs uppercase tracking-wider text-muted-foreground font-light mt-0.5">
              Prioritized by review status, conflicts, and quality risk.
            </p>
          </div>
          <span className="text-[10px] font-mono text-muted-foreground">{products_needing_attention.length} items</span>
        </div>

        {products_needing_attention.length === 0 ? (
          <div className="p-8 border border-border bg-background text-center text-xs text-emerald-500 font-light rounded-none">
            ✓ All products in the catalog are healthy. No items require immediate attention.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-border text-[9px] uppercase tracking-widest text-muted-foreground font-medium">
                  <th className="py-3 px-3">Product / SKU</th>
                  <th className="py-3 px-3">Brand</th>
                  <th className="py-3 px-3">Category</th>
                  <th className="py-3 px-3">Status</th>
                  <th className="py-3 px-3">Quality</th>
                  <th className="py-3 px-3">Issues</th>
                  <th className="py-3 px-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {products_needing_attention.map((item) => (
                  <tr key={item.id} className="hover:bg-accent/40 transition">
                    <td className="py-3 px-3">
                      <div className="font-medium text-foreground">{item.product_name}</div>
                      <div className="text-[10px] text-muted-foreground font-mono">SKU: {item.sku}</div>
                    </td>
                    <td className="py-3 px-3 text-muted-foreground font-light">{item.brand}</td>
                    <td className="py-3 px-3 text-muted-foreground font-light">{item.category}</td>
                    <td className="py-3 px-3">
                      <StatusBadge status={item.status} size="sm" />
                    </td>
                    <td className="py-3 px-3">
                      <ConfidenceBadge confidence={item.quality_score} size="sm" />
                    </td>
                    <td className="py-3 px-3">
                      <div className="space-y-0.5 text-[11px]">
                        {item.open_issues_count > 0 && (
                          <div className="text-amber-500 font-medium">{item.open_issues_count} open issues</div>
                        )}
                        {item.has_conflicts && (
                          <div className="text-destructive font-medium">⚠ Conflict detected</div>
                        )}
                        {item.open_issues_count === 0 && !item.has_conflicts && (
                          <div className="text-muted-foreground font-light">—</div>
                        )}
                      </div>
                    </td>
                    <td className="py-3 px-3 text-right space-x-2">
                      <Link
                        to={`/reviews?product_id=${item.id}`}
                        className="h-8 px-3 bg-amber-500 text-white text-[9px] uppercase tracking-widest font-semibold transition inline-flex items-center gap-1 hover:bg-amber-600 rounded-none"
                      >
                        Review
                      </Link>
                      <Link
                        to={`/catalog?product_id=${item.id}`}
                        className="h-8 px-3 border border-border bg-background text-muted-foreground hover:text-foreground text-[9px] uppercase tracking-widest font-medium transition inline-flex items-center gap-1 rounded-none"
                      >
                        Catalog
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Lowest Quality Products */}
      {worst_products.length > 0 && (
        <div className="p-6 border border-border bg-card space-y-4 rounded-none">
          <div className="flex items-center justify-between border-b border-border pb-3">
            <div>
              <h3 className="font-serif text-xl font-normal text-foreground flex items-center gap-2">
                <TrendingUp className="w-4 h-4 text-destructive" />
                <span>Lowest Quality Products</span>
              </h3>
              <p className="text-xs uppercase tracking-wider text-muted-foreground font-light mt-0.5">
                Bottom products sorted by quality score.
              </p>
            </div>
            <span className="text-[10px] font-mono text-muted-foreground">{worst_products.length} items</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {worst_products.map((item) => (
              <div key={item.id} className="p-4 border border-border bg-background flex items-center justify-between gap-4 rounded-none">
                <div className="min-w-0 flex-1 space-y-1">
                  <div className="font-medium text-foreground text-xs truncate">{item.product_name}</div>
                  <div className="flex items-center gap-2 text-[10px] font-mono text-muted-foreground">
                    <span>{item.brand}</span>
                    <span>•</span>
                    <span>SKU: {item.sku}</span>
                    <span>•</span>
                    <span>{item.category}</span>
                  </div>
                </div>
                <div className="text-right flex items-center gap-3 shrink-0">
                  <ConfidenceBadge confidence={item.quality_score} size="sm" />
                  <Link
                    to={`/catalog?product_id=${item.id}`}
                    className="text-[10px] uppercase tracking-widest font-semibold text-[#9B8F77] hover:text-foreground flex items-center gap-0.5"
                  >
                    <span>Details</span>
                    <ChevronRight className="w-3 h-3" />
                  </Link>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
        </>
      )}
    </div>
  );
};
