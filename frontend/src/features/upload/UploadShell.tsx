import React, { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import {
  UploadCloud,
  AlertTriangle,
  FileText,
  Loader2,
  FolderPlus,
  FileSpreadsheet,
  FileArchive,
  Layers,
  X,
  FileCode,
  Sparkles,
  Database
} from 'lucide-react';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { apiUrl } from '../../lib/api';

interface BatchDocumentStatus {
  document_id: string | null;
  filename: string;
  status: string;
  job_id: string | null;
  mime_type?: string | null;
  file_size?: number | null;
  cached?: boolean;
  error_message?: string | null;
  updated_at: string | null;
}

interface BatchDetail {
  batch_id: string;
  name: string | null;
  status: string;
  total_files: number;
  processed_files: number;
  completed_files: number;
  failed_files: number;
  processing_files: number;
  progress_percentage: number;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  documents: BatchDocumentStatus[];
}

interface RejectedFileResult {
  filename: string;
  error: string;
}

const SUPPORTED_FORMATS = [
  { label: 'PDF', ext: '.pdf', icon: FileText },
  { label: 'Excel', ext: '.xlsx', icon: FileSpreadsheet },
  { label: 'CSV', ext: '.csv', icon: FileSpreadsheet },
  { label: 'Word', ext: '.docx', icon: FileText },
  { label: 'Text/MD', ext: '.txt,.md', icon: FileCode },
  { label: 'JSON/XML', ext: '.json,.xml', icon: FileCode },
  { label: 'HTML', ext: '.html,.htm', icon: FileCode },
  { label: 'ZIP Archive', ext: '.zip', icon: FileArchive },
];

const SUPPORTED_EXTENSIONS = ['.pdf', '.docx', '.xlsx', '.csv', '.txt', '.json', '.xml', '.html', '.htm', '.md', '.zip'];

export const UploadShell: React.FC = () => {
  const [dragActive, setDragActive] = useState(false);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resetCatalogFirst, setResetCatalogFirst] = useState<boolean>(false);

  // Batch progress state
  const [batchId, setBatchId] = useState<string | null>(null);
  const [batchDetail, setBatchDetail] = useState<BatchDetail | null>(null);
  const [rejectedUploads, setRejectedUploads] = useState<RejectedFileResult[]>([]);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);

  // Poll batch status every 1.5s until terminal state
  useEffect(() => {
    if (!batchId) return;

    const pollBatch = async () => {
      try {
        const res = await fetch(apiUrl(`/api/v1/documents/batches/${batchId}`));
        if (!res.ok) throw new Error("Failed to fetch batch status");
        const data: BatchDetail = await res.json();
        setBatchDetail(data);

        // Terminal state reached
        if (['completed', 'partially_completed', 'failed', 'cancelled'].includes(data.status.toLowerCase())) {
          clearInterval(intervalId);
        }
      } catch (err) {
        console.error("Batch polling error:", err);
      }
    };

    pollBatch();
    const intervalId = setInterval(pollBatch, 1500);
    return () => clearInterval(intervalId);
  }, [batchId]);

  const isFileSupported = (file: File): { supported: boolean; reason?: string } => {
    const fileNameLower = file.name.toLowerCase();
    const maxMB = 50;
    const maxBytes = maxMB * 1024 * 1024;

    if (file.size > maxBytes) {
      return { supported: false, reason: `Exceeds max size limit of ${maxMB}MB` };
    }

    const matched = SUPPORTED_EXTENSIONS.some(ext => fileNameLower.endsWith(ext));
    if (!matched) {
      return { supported: false, reason: "Unsupported file format" };
    }

    return { supported: true };
  };

  const handleFilesAdded = (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const newFiles = Array.from(files);
    setSelectedFiles(prev => {
      const existingNames = new Set(prev.map(f => f.name));
      const filtered = newFiles.filter(f => !existingNames.has(f.name));
      return [...prev, ...filtered];
    });
    setError(null);
  };

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFilesAdded(e.dataTransfer.files);
    }
  };

  const removeFile = (index: number) => {
    setSelectedFiles(prev => prev.filter((_, i) => i !== index));
  };

  const clearSelection = () => {
    setSelectedFiles([]);
    setError(null);
  };

  const handleStartBatchUpload = async () => {
    if (selectedFiles.length === 0) return;

    setUploading(true);
    setError(null);
    setRejectedUploads([]);
    setBatchDetail(null);

    if (resetCatalogFirst) {
      try {
        await fetch(apiUrl('/api/v1/products/clear-all'), { method: 'DELETE' });
      } catch (e) {
        console.warn("Failed to reset catalog before upload:", e);
      }
    }

    const formData = new FormData();
    selectedFiles.forEach(file => {
      formData.append("files", file);
    });

    try {
      const res = await fetch(apiUrl('/api/v1/documents/upload-batch'), {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || `Upload failed with HTTP ${res.status}`);
      }

      const result = await res.json();
      setBatchId(result.batch_id);

      if (result.rejected_files && result.rejected_files.length > 0) {
        setRejectedUploads(result.rejected_files);
      }
    } catch (err: any) {
      setError(err?.message || "Failed to initiate batch upload");
    } finally {
      setUploading(false);
    }
  };

  const resetAll = () => {
    setBatchId(null);
    setBatchDetail(null);
    setSelectedFiles([]);
    setRejectedUploads([]);
    setError(null);
  };

  const isTerminalBatch = batchDetail && ['completed', 'partially_completed', 'failed'].includes(batchDetail.status.toLowerCase());

  return (
    <div className="space-y-8 max-w-5xl mx-auto text-foreground rounded-none">
      {/* Header */}
      <div className="space-y-1">
        <div className="inline-flex items-center gap-2 border border-[#9B8F77]/30 bg-[#9B8F77]/5 px-3 py-1 text-[9px] uppercase tracking-widest font-medium text-[#9B8F77] mb-2">
          <Sparkles className="w-3.5 h-3.5" />
          Batch Ingestion Gateway
        </div>
        <h1 className="text-3xl lg:text-4xl font-serif font-normal text-foreground tracking-tight">
          Import & Multi-Source Ingestion
        </h1>
        <p className="text-xs uppercase tracking-wider text-muted-foreground font-light">
          Upload single files, multi-file batches, folder trees, or ZIP archives for autonomous parsing and enrichment.
        </p>
      </div>

      {/* Upload Wizard Form */}
      {!batchId ? (
        <div className="space-y-6">
          {/* Dropzone Card */}
          <div
            onDragEnter={handleDrag}
            onDragLeave={handleDrag}
            onDragOver={handleDrag}
            onDrop={handleDrop}
            className={`p-10 border border-dashed text-center transition-all duration-200 rounded-none relative bg-card ${
              dragActive
                ? 'border-foreground bg-accent/30'
                : 'border-border hover:border-muted-foreground'
            }`}
          >
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept={SUPPORTED_EXTENSIONS.join(',')}
              onChange={(e) => handleFilesAdded(e.target.files)}
              className="hidden"
            />
            <input
              ref={folderInputRef}
              type="file"
              // @ts-ignore
              webkitdirectory=""
              // @ts-ignore
              directory=""
              multiple
              onChange={(e) => handleFilesAdded(e.target.files)}
              className="hidden"
            />

            <div className="w-14 h-14 border border-border bg-background text-[#9B8F77] flex items-center justify-center mx-auto mb-4 rounded-none">
              <UploadCloud className="w-7 h-7" />
            </div>

            <h3 className="text-xl font-serif font-normal text-foreground mb-1">
              Drag and drop your catalog files or ZIP archives
            </h3>
            <p className="text-xs uppercase tracking-wider text-muted-foreground max-w-md mx-auto mb-6 font-light">
              Batch ingestion processes each document independently with automatic content deduplication and partial failure isolation.
            </p>

            <div className="flex flex-wrap items-center justify-center gap-3">
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="h-10 px-6 bg-foreground text-background border border-foreground hover:bg-transparent hover:text-foreground text-[10px] uppercase tracking-widest font-semibold transition duration-150 rounded-none flex items-center gap-2"
              >
                <FileText className="w-3.5 h-3.5" />
                <span>Select Files / ZIP</span>
              </button>

              <button
                type="button"
                onClick={() => folderInputRef.current?.click()}
                className="h-10 px-6 bg-background text-muted-foreground hover:text-foreground border border-border hover:bg-card text-[10px] uppercase tracking-widest font-semibold transition duration-150 rounded-none flex items-center gap-2"
              >
                <FolderPlus className="w-3.5 h-3.5" />
                <span>Upload Folder</span>
              </button>
            </div>
          </div>

          {/* Supported Formats Legend */}
          <div className="p-5 border border-border bg-card rounded-none">
            <div className="text-[10px] font-medium uppercase tracking-widest text-[#9B8F77] mb-3">
              Supported Ingestion Formats
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
              {SUPPORTED_FORMATS.map((fmt) => {
                const Icon = fmt.icon;
                return (
                  <div
                    key={fmt.label}
                    className="flex items-center gap-2.5 p-2.5 border border-border bg-background/60 text-xs rounded-none"
                  >
                    <Icon className="w-4 h-4 text-[#9B8F77] shrink-0" />
                    <div>
                      <div className="font-medium text-foreground text-[11px]">{fmt.label}</div>
                      <div className="text-[9px] text-muted-foreground font-mono">{fmt.ext}</div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Selected Files Staging List */}
          {selectedFiles.length > 0 && (
            <div className="p-6 border border-border bg-card space-y-4 rounded-none">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-serif text-lg font-normal text-foreground">
                    Selected Files Staging ({selectedFiles.length})
                  </h3>
                  <span className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
                    Total: {(selectedFiles.reduce((acc, f) => acc + f.size, 0) / (1024 * 1024)).toFixed(2)} MB
                  </span>
                </div>

                <div className="flex items-center gap-4 flex-wrap">
                  <label className="flex items-center gap-2 cursor-pointer text-xs text-muted-foreground hover:text-foreground select-none">
                    <input
                      type="checkbox"
                      checked={resetCatalogFirst}
                      onChange={(e) => setResetCatalogFirst(e.target.checked)}
                      className="accent-[#9B8F77]"
                    />
                    <span className="text-[10px] uppercase tracking-wider">Clean Slate (Reset Catalog First)</span>
                  </label>
                  <button
                    onClick={clearSelection}
                    className="text-[10px] uppercase tracking-widest text-muted-foreground hover:text-foreground"
                  >
                    Clear Selection
                  </button>
                  <button
                    onClick={handleStartBatchUpload}
                    disabled={uploading}
                    className="h-10 px-6 bg-foreground text-background border border-foreground hover:bg-transparent hover:text-foreground text-[10px] uppercase tracking-widest font-semibold transition duration-150 rounded-none flex items-center gap-2 disabled:opacity-50"
                  >
                    {uploading ? (
                      <>
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        <span>Starting Ingestion...</span>
                      </>
                    ) : (
                      <>
                        <Sparkles className="w-3.5 h-3.5 text-[#9B8F77]" />
                        <span>Start Batch Import ({selectedFiles.length})</span>
                      </>
                    )}
                  </button>
                </div>
              </div>

              {/* Table of selected files */}
              <div className="max-h-64 overflow-y-auto divide-y divide-border pr-1">
                {selectedFiles.map((file, idx) => {
                  const validation = isFileSupported(file);
                  return (
                    <div key={`${file.name}-${idx}`} className="py-2.5 flex items-center justify-between gap-4">
                      <div className="flex items-center gap-3 min-w-0">
                        <FileText className="w-4 h-4 text-muted-foreground shrink-0" />
                        <span className="text-xs font-light text-foreground truncate">{file.name}</span>
                        <span className="text-[10px] font-mono text-muted-foreground">
                          {(file.size / 1024).toFixed(1)} KB
                        </span>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        {validation.supported ? (
                          <span className="text-[9px] font-mono uppercase tracking-widest px-2 py-0.5 border border-border bg-background text-emerald-500">
                            Valid
                          </span>
                        ) : (
                          <span className="text-[9px] font-mono uppercase tracking-widest px-2 py-0.5 border border-destructive/40 bg-destructive/10 text-destructive">
                            {validation.reason}
                          </span>
                        )}
                        <button
                          onClick={() => removeFile(idx)}
                          className="p-1 text-muted-foreground hover:text-foreground"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {error && (
            <div className="p-4 border border-destructive/40 bg-destructive/10 flex items-center gap-3 text-xs text-destructive rounded-none">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}
        </div>
      ) : (
        /* Active Batch Progress Dashboard */
        <div className="space-y-6">
          <div className="p-6 border border-border bg-card space-y-6 rounded-none">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="text-[9px] font-light uppercase tracking-widest text-muted-foreground">
                    Batch Ingestion Job
                  </span>
                  <span className="text-[10px] font-mono text-[#9B8F77] px-2 py-0.5 border border-border bg-background">
                    {batchId.slice(0, 8)}...
                  </span>
                </div>
                <h2 className="text-2xl font-serif font-normal text-foreground">
                  {batchDetail ? `${batchDetail.progress_percentage}% Completed` : 'Initializing Batch...'}
                </h2>
              </div>

              <div className="flex items-center gap-3">
                {isTerminalBatch ? (
                  <>
                    <button
                      onClick={resetAll}
                      className="h-10 px-5 border border-border bg-background text-xs uppercase tracking-widest font-medium text-muted-foreground hover:text-foreground hover:bg-card transition"
                    >
                      New Import
                    </button>
                    <Link
                      to="/catalog"
                      className="h-10 px-5 bg-foreground text-background border border-foreground hover:bg-transparent hover:text-foreground text-xs uppercase tracking-widest font-semibold transition flex items-center gap-2"
                    >
                      <Database className="w-3.5 h-3.5" />
                      <span>View Products</span>
                    </Link>
                  </>
                ) : (
                  <div className="flex items-center gap-2 text-xs font-mono uppercase tracking-wider text-[#9B8F77] animate-pulse">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Processing Ingestion Stages...</span>
                  </div>
                )}
              </div>
            </div>

            {/* Progress Bar */}
            <div className="space-y-2">
              <div className="h-2 bg-background border border-border rounded-none overflow-hidden">
                <div
                  className="h-full bg-foreground transition-all duration-300"
                  style={{ width: `${batchDetail?.progress_percentage ?? 0}%` }}
                />
              </div>
              <div className="flex justify-between text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
                <span>
                  {batchDetail ? `${batchDetail.completed_files} of ${batchDetail.total_files} completed` : '0 files'}
                </span>
                <span>{batchDetail?.failed_files ?? 0} failed</span>
              </div>
            </div>

            {/* Metrics Counters */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2 border-t border-border text-center">
              <div className="p-3 border border-border bg-background rounded-none">
                <div className="text-xl font-mono text-foreground">{batchDetail?.total_files ?? 0}</div>
                <div className="text-[9px] text-muted-foreground uppercase tracking-widest font-light">Total Items</div>
              </div>
              <div className="p-3 border border-border bg-background rounded-none">
                <div className="text-xl font-mono text-emerald-500">{batchDetail?.completed_files ?? 0}</div>
                <div className="text-[9px] text-muted-foreground uppercase tracking-widest font-light">Completed</div>
              </div>
              <div className="p-3 border border-border bg-background rounded-none">
                <div className="text-xl font-mono text-[#9B8F77]">{batchDetail?.processing_files ?? 0}</div>
                <div className="text-[9px] text-muted-foreground uppercase tracking-widest font-light">Processing</div>
              </div>
              <div className="p-3 border border-border bg-background rounded-none">
                <div className="text-xl font-mono text-destructive">{batchDetail?.failed_files ?? 0}</div>
                <div className="text-[9px] text-muted-foreground uppercase tracking-widest font-light">Failed</div>
              </div>
            </div>
          </div>

          {/* Rejected Uploads Banner */}
          {rejectedUploads.length > 0 && (
            <div className="p-4 border border-destructive/40 bg-destructive/10 space-y-2 rounded-none">
              <div className="flex items-center gap-2 text-destructive text-xs font-semibold uppercase tracking-wider">
                <AlertTriangle className="w-4 h-4" />
                <span>{rejectedUploads.length} Files Rejected at Ingress</span>
              </div>
              <div className="divide-y divide-destructive/20 text-xs text-foreground font-mono">
                {rejectedUploads.map((rej, i) => (
                  <div key={i} className="py-1.5 flex justify-between">
                    <span>{rej.filename}</span>
                    <span className="text-destructive">{rej.error}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Per-Document Processing Cards */}
          <div className="p-6 border border-border bg-card space-y-4 rounded-none">
            <h3 className="font-serif text-lg font-normal text-foreground flex items-center gap-2">
              <Layers className="w-4 h-4 text-[#9B8F77]" />
              <span>Document Processing Items ({batchDetail?.documents.length ?? 0})</span>
            </h3>

            <div className="divide-y divide-border">
              {(batchDetail?.documents ?? []).map((doc, idx) => (
                <div key={`${doc.filename}-${idx}`} className="py-3 flex items-center justify-between gap-4">
                  <div className="min-w-0 space-y-0.5">
                    <div className="text-xs font-medium text-foreground truncate flex items-center gap-2">
                      <span>{doc.filename}</span>
                      {doc.cached && (
                        <span className="text-[9px] font-mono uppercase tracking-widest px-1.5 py-0.5 border border-border bg-background text-[#9B8F77]">
                          Cached / Deduplicated
                        </span>
                      )}
                    </div>
                    <div className="text-[10px] text-muted-foreground font-mono">
                      {doc.document_id ? `ID: ${doc.document_id.slice(0, 8)}...` : 'Rejected'}
                    </div>
                  </div>
                  <div className="shrink-0">
                    <StatusBadge status={doc.status} size="sm" />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
