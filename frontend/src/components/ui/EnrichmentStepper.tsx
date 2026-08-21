import React from 'react';
import { Sparkles, Layers, ShieldCheck, Database, CheckCircle2 } from 'lucide-react';

interface EnrichmentStepperProps {
  status?: string;
  qualityScore?: number;
  className?: string;
}

export const EnrichmentStepper: React.FC<EnrichmentStepperProps> = ({
  status = 'verified',
  qualityScore = 85,
  className = '',
}) => {
  const stages = [
    {
      id: 'raw',
      label: 'Stage 01',
      title: 'Raw Multi-Format Ingestion',
      desc: 'OCR & PDF parsing to IR blocks',
      icon: Database,
      completed: true,
    },
    {
      id: 'specs',
      label: 'Stage 02',
      title: 'Normalized Attributes',
      desc: 'Deterministic extraction & SI units',
      icon: Layers,
      completed: true,
    },
    {
      id: 'enrichment',
      label: 'Stage 03',
      title: 'AI Commerce Enrichment',
      desc: 'Executive summaries, bullet features & SEO',
      icon: Sparkles,
      completed: qualityScore > 50,
    },
    {
      id: 'audit',
      label: 'Stage 04',
      title: 'Evidence Audit & Provenance',
      desc: 'Verbatim citations & confidence scoring',
      icon: ShieldCheck,
      completed: status.toLowerCase() === 'verified' || qualityScore > 75,
    },
  ];

  return (
    <div className={`border border-border bg-card p-6 rounded-none space-y-4 ${className}`}>
      <div className="flex items-center justify-between border-b border-border pb-3">
        <div className="space-y-0.5">
          <div className="text-[9px] font-medium uppercase tracking-widest text-[#9B8F77]">
            Intelligence Pipeline Transformation
          </div>
          <h4 className="text-base font-serif font-normal text-foreground">
            End-to-End Autonomous Enrichment Pipeline
          </h4>
        </div>
        <span className="font-mono text-xs text-foreground font-semibold px-2 py-0.5 border border-border bg-background">
          Quality: {Math.round(qualityScore)}%
        </span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 pt-1">
        {stages.map((stg) => {
          const Icon = stg.icon;
          return (
            <div
              key={stg.id}
              className={`p-3.5 border transition rounded-none relative space-y-2 ${
                stg.completed
                  ? 'border-border bg-background/80'
                  : 'border-border/50 bg-background/20 opacity-60'
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="text-[9px] font-mono uppercase tracking-widest text-[#9B8F77]">
                  {stg.label}
                </span>
                {stg.completed ? (
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                ) : (
                  <span className="w-2 h-2 border border-muted-foreground rounded-none" />
                )}
              </div>

              <div className="flex items-start gap-2 pt-1">
                <Icon className="w-4 h-4 text-[#9B8F77] shrink-0 mt-0.5" />
                <div>
                  <div className="text-xs font-serif font-normal text-foreground leading-tight">
                    {stg.title}
                  </div>
                  <div className="text-[10px] text-muted-foreground font-light mt-0.5">
                    {stg.desc}
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
