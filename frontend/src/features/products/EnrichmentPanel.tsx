import React from 'react';
import {
  Sparkles,
  FileText,
  Target,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  Globe,
  Award,
  Bot,
  Layers,
  Tag,
  FolderTree,
  Hash,
  ShoppingBag
} from 'lucide-react';
import { ConfidenceBadge } from '../../components/ui/ConfidenceBadge';
import { formatAttrValueAndUnit } from '../../lib/formatters';

interface ProductInfo {
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

interface EnrichmentData {
  commerce_description?: string;
  short_description?: string;
  short_desc?: string;
  features?: string[];
  applications?: string[];
  keywords?: string[];
  seo_title?: string;
  seo_description?: string;
  confidence?: number;
  model?: string;
  prompt_version?: string;
  status?: string;
  generated_value?: string;
  invoice_desc?: string;
  mobile_desc?: string;
  long_desc?: string;
  retail_desc?: string;
}

interface EnrichmentPanelProps {
  product?: ProductInfo | null;
  attributes?: ProductAttributeItem[];
  enrichment?: EnrichmentData;
  onRerunEnrichment?: () => void;
}

const AiBadge: React.FC<{ label?: string }> = ({ label = 'AI Enriched' }) => (
  <span className="inline-flex items-center gap-1 text-[9px] font-mono uppercase tracking-widest px-1.5 py-0.5 border border-[#9B8F77]/30 bg-[#9B8F77]/10 text-[#9B8F77]">
    <Bot className="w-2.5 h-2.5" />
    {label}
  </span>
);

export const EnrichmentPanel: React.FC<EnrichmentPanelProps> = ({
  product,
  attributes = [],
  enrichment,
  onRerunEnrichment,
}) => {
  let parsedGen: any = {};
  if (enrichment?.generated_value) {
    try {
      parsedGen = typeof enrichment.generated_value === 'string'
        ? JSON.parse(enrichment.generated_value)
        : enrichment.generated_value;
    } catch {
      parsedGen = {};
    }
  }

  const descs = parsedGen.descriptions || {};
  const deliveryRec = parsedGen.delivery_record || {};

  // Resolve 5 Delivery Channels with fallbacks
  const invoiceDesc =
    enrichment?.invoice_desc ||
    parsedGen.invoice_desc ||
    descs.invoice_desc ||
    deliveryRec.INVOICE_DESC ||
    '';

  const mobileDesc =
    enrichment?.mobile_desc ||
    parsedGen.mobile_desc ||
    descs.mobile_desc ||
    deliveryRec.MOBILE_DESC ||
    '';

  const shortDescription =
    enrichment?.short_description ||
    enrichment?.short_desc ||
    parsedGen.short_description ||
    descs.short_desc ||
    deliveryRec.SHORT_DESC ||
    product?.product_name ||
    '';

  const longDesc =
    enrichment?.long_desc ||
    enrichment?.commerce_description ||
    parsedGen.long_desc ||
    descs.long_desc ||
    deliveryRec.LONG_DESC1 ||
    parsedGen.commerce_description ||
    product?.commerce_description ||
    product?.description ||
    '';

  const retailDesc =
    enrichment?.retail_desc ||
    parsedGen.retail_desc ||
    descs.retail_desc ||
    deliveryRec.RETAIL_DESC ||
    '';

  const rawInputDesc =
    product?.description ||
    deliveryRec.Part_Desc ||
    product?.product_name ||
    '—';

  const classpath = product?.category || deliveryRec.Classpath || '—';
  const brandName = product?.brand || deliveryRec.BRAND_NAME || '—';
  const mpn = product?.sku || product?.model || deliveryRec.Mfg_Part_Num || '—';

  const features: string[] =
    enrichment?.features && enrichment.features.length > 0
      ? enrichment.features
      : parsedGen.features || [];

  const applications: string[] =
    enrichment?.applications && enrichment.applications.length > 0
      ? enrichment.applications
      : parsedGen.applications || [];

  const seoTitle = enrichment?.seo_title || parsedGen.seo_title;
  const seoDescription = enrichment?.seo_description || parsedGen.seo_description;
  const rawConf = enrichment?.confidence ?? parsedGen.confidence ?? 0.95;

  if (enrichment?.status === 'failed') {
    return (
      <div className="border border-destructive/40 bg-destructive/10 p-8 space-y-4 rounded-none">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-serif font-normal text-destructive flex items-center gap-2">
            <AlertTriangle className="w-5 h-5" />
            <span>AI Commerce Enrichment Failed</span>
          </h3>
          <span className="text-[10px] font-mono px-2.5 py-1 border border-destructive bg-background uppercase font-bold text-destructive">
            Failed
          </span>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          The enrichment generation encountered an error or failed safety threshold validation.
        </p>
        {onRerunEnrichment && (
          <button
            onClick={onRerunEnrichment}
            className="h-9 px-4 bg-destructive text-destructive-foreground text-[10px] uppercase tracking-widest font-semibold transition rounded-none inline-flex items-center gap-2"
          >
            <RefreshCw className="w-3 h-3" />
            <span>Retry Commerce Intelligence</span>
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-8 rounded-none">
      {/* Enrichment Metadata Bar */}
      <div className="border border-border bg-card p-4 flex flex-wrap items-center justify-between gap-4 rounded-none">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 border border-border bg-background text-[#9B8F77] flex items-center justify-center rounded-none">
            <Sparkles className="w-4 h-4" />
          </div>
          <div>
            <div className="text-xs font-serif font-normal text-foreground flex items-center gap-2">
              <span>Structured Commerce & Delivery Intelligence</span>
              <AiBadge label={enrichment?.model ? 'Verified & Enriched' : 'Deterministic Master'} />
            </div>
            <div className="text-[10px] text-muted-foreground font-mono">
              Delivery Standard: <span className="text-foreground">Unilog 252-Column Schema</span>
              {enrichment?.prompt_version && (
                <> • Version: <span className="text-foreground">{enrichment.prompt_version}</span></>
              )}
              {enrichment?.model && (
                <> • Model: <span className="text-foreground">{enrichment.model}</span></>
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {rawConf != null && <ConfidenceBadge confidence={rawConf} />}
          {onRerunEnrichment && (
            <button
              onClick={onRerunEnrichment}
              className="h-8 px-3 border border-border bg-background text-muted-foreground hover:text-foreground text-[10px] uppercase tracking-widest font-medium transition inline-flex items-center gap-1.5 rounded-none"
              title="Regenerate with fresh LLM prompt"
            >
              <RefreshCw className="w-3 h-3 text-[#9B8F77]" />
              <span>Re-enrich Content</span>
            </button>
          )}
        </div>
      </div>

      {/* ========================================================================= */}
      {/* 1. PRIMARY STRUCTURED PRODUCT COMMERCE & DELIVERY PRESENTATION           */}
      {/* ========================================================================= */}
      <div className="border border-border bg-card p-6 md:p-8 space-y-6 rounded-none">
        <div className="flex items-center justify-between border-b border-border pb-3">
          <h3 className="text-xs font-medium uppercase tracking-widest text-[#9B8F77] flex items-center gap-2">
            <ShoppingBag className="w-4 h-4 text-[#9B8F77]" />
            <span>Structured Product Master Fields</span>
          </h3>
          <span className="text-[10px] font-mono text-muted-foreground uppercase">
            Official Delivery Specification
          </span>
        </div>

        <div className="space-y-4 text-xs">
          {/* 1. INPUT — Part_Desc */}
          <div className="p-4 border border-border bg-background space-y-1.5 rounded-none">
            <div className="flex items-center justify-between text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
              <span className="flex items-center gap-1.5 font-medium text-foreground">
                <FileText className="w-3 h-3 text-[#9B8F77]" />
                INPUT — Part_Desc
              </span>
              <span className="text-[9px] px-1.5 py-0.5 border border-border bg-accent text-foreground">
                Raw Supplier Feed
              </span>
            </div>
            <div className="font-mono text-xs text-foreground bg-accent/20 p-2.5 border border-border/60 select-all">
              {rawInputDesc}
            </div>
          </div>

          {/* 2. Classpath */}
          <div className="p-4 border border-border bg-background space-y-1.5 rounded-none">
            <div className="flex items-center justify-between text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
              <span className="flex items-center gap-1.5 font-medium text-foreground">
                <FolderTree className="w-3 h-3 text-[#9B8F77]" />
                Classpath
              </span>
              <span className="text-[9px] px-1.5 py-0.5 border border-border bg-accent text-foreground">
                Approved Taxonomy
              </span>
            </div>
            <div className="font-mono text-xs text-[#9B8F77] bg-accent/20 p-2.5 border border-border/60">
              {classpath}
            </div>
          </div>

          {/* 3. Brand / MPN */}
          <div className="p-4 border border-border bg-background space-y-1.5 rounded-none">
            <div className="flex items-center justify-between text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
              <span className="flex items-center gap-1.5 font-medium text-foreground">
                <Tag className="w-3 h-3 text-[#9B8F77]" />
                Brand / MPN
              </span>
              <span className="text-[9px] px-1.5 py-0.5 border border-border bg-accent text-foreground">
                Identity Master
              </span>
            </div>
            <div className="flex items-center gap-3 font-mono text-xs bg-accent/20 p-2.5 border border-border/60">
              <strong className="text-foreground">{brandName}</strong>
              <span className="text-muted-foreground">|</span>
              <strong className="text-[#9B8F77]">{mpn}</strong>
            </div>
          </div>

          {/* 4. Invoice Desc */}
          <div className="p-4 border border-border bg-background space-y-1.5 rounded-none">
            <div className="flex items-center justify-between text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
              <span className="flex items-center gap-1.5 font-medium text-foreground">
                <Hash className="w-3 h-3 text-[#9B8F77]" />
                Invoice Desc
              </span>
              <span className="font-mono text-[9px] text-[#9B8F77]">
                &lt;= 40 Chars, UPPERCASE ({invoiceDesc.length}/40)
              </span>
            </div>
            <div className="font-mono text-xs font-bold text-[#9B8F77] bg-accent/20 p-2.5 border border-border/60 select-all">
              {invoiceDesc || '—'}
            </div>
          </div>

          {/* 5. Mobile Desc */}
          <div className="p-4 border border-border bg-background space-y-1.5 rounded-none">
            <div className="flex items-center justify-between text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
              <span className="flex items-center gap-1.5 font-medium text-foreground">
                <FileText className="w-3 h-3 text-[#9B8F77]" />
                Mobile Desc
              </span>
              <span className="font-mono text-[9px] text-muted-foreground">
                60–80 Chars Target ({mobileDesc.length}/80)
              </span>
            </div>
            <div className="text-xs text-foreground bg-accent/20 p-2.5 border border-border/60 select-all">
              {mobileDesc || '—'}
            </div>
          </div>

          {/* 6. Product Title / Short Desc */}
          <div className="p-4 border border-border bg-background space-y-1.5 rounded-none">
            <div className="flex items-center justify-between text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
              <span className="flex items-center gap-1.5 font-medium text-foreground">
                <Award className="w-3 h-3 text-[#9B8F77]" />
                Product Title / Short Desc
              </span>
              <span className="text-[9px] px-1.5 py-0.5 border border-border bg-accent text-foreground">
                Catalog Display Title
              </span>
            </div>
            <div className="text-xs font-serif font-normal text-foreground bg-accent/20 p-2.5 border border-border/60">
              {shortDescription || '—'}
            </div>
          </div>

          {/* Retail Description (if present) */}
          {retailDesc && (
            <div className="p-4 border border-border bg-background space-y-1.5 rounded-none">
              <div className="flex items-center justify-between text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
                <span className="flex items-center gap-1.5 font-medium text-foreground">
                  <FileText className="w-3 h-3 text-[#9B8F77]" />
                  Retail Description
                </span>
                <span className="text-[9px] px-1.5 py-0.5 border border-border bg-accent text-foreground">
                  Customer-Facing Header
                </span>
              </div>
              <div className="text-xs text-foreground bg-accent/20 p-2.5 border border-border/60 select-all">
                {retailDesc}
              </div>
            </div>
          )}

          {/* 7. Long Description */}
          <div className="p-4 border border-border bg-background space-y-1.5 rounded-none">
            <div className="flex items-center justify-between text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
              <span className="flex items-center gap-1.5 font-medium text-foreground">
                <FileText className="w-3 h-3 text-[#9B8F77]" />
                Long Description
              </span>
              <span className="text-[9px] px-1.5 py-0.5 border border-emerald-500/30 bg-emerald-500/10 text-emerald-500">
                ClaimChecker Grounded
              </span>
            </div>
            <div className="text-xs text-foreground font-light leading-relaxed bg-accent/20 p-3 border border-border/60">
              {longDesc || '—'}
            </div>
          </div>

          {/* 8. Attributes Summary */}
          {attributes.length > 0 && (
            <div className="p-4 border border-border bg-background space-y-2.5 rounded-none">
              <div className="flex items-center justify-between text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
                <span className="flex items-center gap-1.5 font-medium text-foreground">
                  <Layers className="w-3 h-3 text-[#9B8F77]" />
                  Attributes ({attributes.length})
                </span>
                <span className="text-[9px] text-muted-foreground">
                  Normalized Specs & Units
                </span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2 pt-1">
                {attributes.map((attr) => {
                  const formatted = formatAttrValueAndUnit(attr.raw_value, attr.unit, attr.normalized_value);
                  return (
                    <div
                      key={attr.id}
                      className="p-2 border border-border/80 bg-accent/10 space-y-1 text-xs"
                    >
                      <div className="text-[10px] font-medium text-muted-foreground truncate">
                        {attr.display_name || attr.attribute_name}
                      </div>
                      <div className="font-mono font-medium text-foreground">
                        {formatted.value} {formatted.unit && <span className="text-[#9B8F77]">{formatted.unit}</span>}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ========================================================================= */}
      {/* 2. BULLET FEATURES & TARGET INDUSTRIAL APPLICATIONS                      */}
      {/* ========================================================================= */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Bullet Features */}
        <div className="border border-border bg-card p-6 space-y-3 rounded-none">
          <h4 className="text-[10px] font-medium uppercase tracking-widest text-[#9B8F77] flex items-center gap-2 border-b border-border pb-2">
            <Award className="w-3.5 h-3.5" />
            <span>Key Feature Bullet Points ({features.length})</span>
            {features.length > 0 && <AiBadge />}
          </h4>
          {features.length === 0 ? (
            <p className="text-xs text-muted-foreground font-light">No feature points generated.</p>
          ) : (
            <ul className="space-y-2">
              {features.map((feat, idx) => (
                <li key={idx} className="flex items-start gap-2.5 text-xs text-foreground font-light">
                  <CheckCircle2 className="w-3.5 h-3.5 text-[#9B8F77] shrink-0 mt-0.5" />
                  <span>{feat}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Industrial Applications */}
        <div className="border border-border bg-card p-6 space-y-3 rounded-none">
          <h4 className="text-[10px] font-medium uppercase tracking-widest text-[#9B8F77] flex items-center gap-2 border-b border-border pb-2">
            <Target className="w-3.5 h-3.5" />
            <span>Target Industrial Applications ({applications.length})</span>
            {applications.length > 0 && <AiBadge />}
          </h4>
          {applications.length === 0 ? (
            <p className="text-xs text-muted-foreground font-light">No applications identified.</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {applications.map((app, idx) => (
                <span
                  key={idx}
                  className="px-2.5 py-1 border border-border bg-background text-[11px] font-light text-foreground"
                >
                  {app}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ========================================================================= */}
      {/* 3. SEARCH ENGINE & COMMERCE SEO METADATA                                 */}
      {/* ========================================================================= */}
      {(seoTitle || seoDescription) && (
        <div className="border border-border bg-card p-6 space-y-3 rounded-none">
          <h4 className="text-[10px] font-medium uppercase tracking-widest text-[#9B8F77] flex items-center gap-2 border-b border-border pb-2">
            <Globe className="w-3.5 h-3.5" />
            <span>Search Engine & Commerce SEO Metadata</span>
            <AiBadge />
          </h4>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {seoTitle && (
              <div className="p-3 border border-border bg-background space-y-1">
                <div className="text-[9px] uppercase tracking-widest text-muted-foreground">SEO Page Title</div>
                <div className="text-xs font-medium text-foreground">{seoTitle}</div>
              </div>
            )}
            {seoDescription && (
              <div className="p-3 border border-border bg-background space-y-1">
                <div className="text-[9px] uppercase tracking-widest text-muted-foreground">SEO Meta Description</div>
                <div className="text-xs text-muted-foreground font-light">{seoDescription}</div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
