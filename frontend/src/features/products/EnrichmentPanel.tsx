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
  Bot
} from 'lucide-react';
import { ConfidenceBadge } from '../../components/ui/ConfidenceBadge';

interface EnrichmentData {
  commerce_description?: string;
  short_description?: string;
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
}

interface EnrichmentPanelProps {
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
  enrichment,
  onRerunEnrichment,
}) => {
  if (!enrichment) {
    return (
      <div className="border border-border bg-card p-10 text-center space-y-4 rounded-none">
        <Sparkles className="w-8 h-8 text-[#9B8F77] mx-auto" />
        <h4 className="text-xl font-serif font-normal text-foreground">No AI Commerce Content Generated Yet</h4>
        <p className="text-xs uppercase tracking-wider text-muted-foreground max-w-md mx-auto font-light">
          Generate publication-grade commerce descriptions, bulleted features, and SEO titles backed by verified product specifications.
        </p>
        {onRerunEnrichment && (
          <button
            onClick={onRerunEnrichment}
            className="h-10 px-6 bg-foreground text-background border border-foreground hover:bg-transparent hover:text-foreground text-[10px] uppercase tracking-widest font-semibold transition duration-150 rounded-none inline-flex items-center gap-2"
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span>Generate Commerce Intelligence</span>
          </button>
        )}
      </div>
    );
  }

  let parsedGen: any = {};
  if (enrichment.generated_value) {
    try {
      parsedGen = typeof enrichment.generated_value === 'string'
        ? JSON.parse(enrichment.generated_value)
        : enrichment.generated_value;
    } catch {
      parsedGen = {};
    }
  }

  const commerceDescription = enrichment.commerce_description || parsedGen.commerce_description;
  const shortDescription = enrichment.short_description || parsedGen.short_description;
  const features: string[] = (enrichment.features && enrichment.features.length > 0)
    ? enrichment.features
    : (parsedGen.features || []);
  const applications: string[] = (enrichment.applications && enrichment.applications.length > 0)
    ? enrichment.applications
    : (parsedGen.applications || []);
  const seoTitle = enrichment.seo_title || parsedGen.seo_title;
  const seoDescription = enrichment.seo_description || parsedGen.seo_description;
  const invoiceDesc = enrichment.invoice_desc || parsedGen.invoice_desc;
  const mobileDesc = enrichment.mobile_desc || parsedGen.mobile_desc;
  const retailDesc = parsedGen.retail_desc;
  const longDesc = parsedGen.long_desc || commerceDescription;

  const rawConf = enrichment.confidence ?? parsedGen.confidence ?? null;

  if (enrichment.status === 'failed') {
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
    <div className="space-y-6 rounded-none">
      {/* Enrichment Metadata Bar */}
      <div className="border border-border bg-card p-4 flex flex-wrap items-center justify-between gap-4 rounded-none">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 border border-border bg-background text-[#9B8F77] flex items-center justify-center rounded-none">
            <Sparkles className="w-4 h-4" />
          </div>
          <div>
            <div className="text-xs font-serif font-normal text-foreground flex items-center gap-2">
              <span>AI Commerce Intelligence Suite</span>
              <AiBadge label="AI Generated" />
            </div>
            <div className="text-[10px] text-muted-foreground font-mono">
              Prompt Version: <span className="text-foreground">{enrichment.prompt_version || 'v1.0'}</span>
              {enrichment.model && (
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
              <span>Regenerate</span>
            </button>
          )}
        </div>
      </div>

      {/* 5-Channel Content Descriptions */}
      {(invoiceDesc || mobileDesc || shortDescription || longDesc || retailDesc) && (
        <div className="space-y-4">
          <h3 className="text-xs font-medium uppercase tracking-widest text-[#9B8F77] flex items-center gap-2">
            <FileText className="w-3.5 h-3.5" />
            <span>Multi-Channel Content Descriptions</span>
            <AiBadge />
          </h3>

          {/* Invoice Description */}
          {invoiceDesc && (
            <div className="p-3 border border-border bg-background space-y-1 rounded-none">
              <div className="flex items-center justify-between text-[9px] font-medium uppercase tracking-widest text-muted-foreground">
                <span>Invoice Desc (ERP / Till Receipt &lt;= 40 chars, UPPERCASE)</span>
                <span className="font-mono text-foreground">{invoiceDesc.length}/40</span>
              </div>
              <div className="font-mono text-xs font-bold text-[#9B8F77]">
                {invoiceDesc}
              </div>
            </div>
          )}

          {/* Mobile Description */}
          {mobileDesc && (
            <div className="p-3 border border-border bg-background space-y-1 rounded-none">
              <div className="flex items-center justify-between text-[9px] font-medium uppercase tracking-widest text-muted-foreground">
                <span>Mobile Desc (App Compact List &lt;= 80 chars)</span>
                <span className="font-mono text-foreground">{mobileDesc.length}/80</span>
              </div>
              <div className="text-xs text-foreground font-light">
                {mobileDesc}
              </div>
            </div>
          )}

          {/* Short Description */}
          {shortDescription && (
            <div className="p-3 border border-border bg-background space-y-1 rounded-none">
              <div className="text-[9px] font-medium uppercase tracking-widest text-muted-foreground">
                Short Marketing Blurb
              </div>
              <div className="text-xs text-foreground italic font-light">{shortDescription}</div>
            </div>
          )}

          {/* Long / Commerce Description */}
          {longDesc && (
            <div className="p-3 border border-border bg-background space-y-1 rounded-none">
              <div className="text-[9px] font-medium uppercase tracking-widest text-muted-foreground">
                Long Description (Catalog Page Marketing Copy)
              </div>
              <div className="text-xs text-foreground font-light leading-relaxed">
                {longDesc}
              </div>
            </div>
          )}

          {/* Retail Description */}
          {retailDesc && (
            <div className="p-3 border border-border bg-background space-y-1 rounded-none">
              <div className="text-[9px] font-medium uppercase tracking-widest text-muted-foreground">
                Retail Title (Customer-Facing Header)
              </div>
              <div className="text-xs text-foreground font-light">
                {retailDesc}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Executive Commerce Summary (fallback if no channel descs) */}
      {!invoiceDesc && !mobileDesc && commerceDescription && (
        <div className="border border-border bg-card p-6 space-y-3 rounded-none">
          <div className="flex items-center justify-between border-b border-border pb-2">
            <h4 className="text-[10px] font-medium uppercase tracking-widest text-[#9B8F77] flex items-center gap-2">
              <FileText className="w-3.5 h-3.5" />
              <span>Executive Commerce Description</span>
              <AiBadge />
            </h4>
          </div>
          <p className="text-sm text-foreground leading-relaxed font-light">
            {commerceDescription}
          </p>
        </div>
      )}

      {/* Bullet Features & Target Applications */}
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

      {/* SEO & Publication Metadata */}
      {(seoTitle || seoDescription) && (
        <div className="border border-border bg-card p-6 space-y-3 rounded-none">
          <h4 className="text-[10px] font-medium uppercase tracking-widest text-[#9B8F77] flex items-center gap-2 border-b border-border pb-2">
            <Globe className="w-3.5 h-3.5" />
            <span>Search Engine & Commerce SEO</span>
            <AiBadge />
          </h4>
          {seoTitle && (
            <div>
              <div className="text-[9px] uppercase tracking-widest text-muted-foreground">SEO Page Title</div>
              <div className="text-xs font-medium text-foreground">{seoTitle}</div>
            </div>
          )}
          {seoDescription && (
            <div>
              <div className="text-[9px] uppercase tracking-widest text-muted-foreground">SEO Meta Description</div>
              <div className="text-xs text-muted-foreground font-light">{seoDescription}</div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
