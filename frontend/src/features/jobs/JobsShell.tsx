import React, { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Activity, FileText, AlertTriangle, Eye, RefreshCw, Loader2, Trash2 } from 'lucide-react';
import { formatApiDateTime, parseApiDate } from '../../lib/dates';
import { apiUrl } from '../../lib/api';

interface DocumentInfo {
  id: string;
  filename: string;
  storage_backend: string;
  storage_key: string;
  file_hash: string;
  content_hash: string | null;
  mime_type: string;
  file_size: number;
  page_count: number | null;
  status: string;
  parser_name: string | null;
  parser_version: string | null;
  parsed_at: string | null;
  created_at: string;
}

export const JobsShell: React.FC = () => {
  const queryClient = useQueryClient();
  const [clearing, setClearing] = useState(false);
  const [reprocessingId, setReprocessingId] = useState<string | null>(null);

  // JSON Inspector Modal state
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);

  // 1. Fetch Documents with React Query
  const {
    data: documents = [],
    isLoading: loading,
    error: queryError,
    refetch: fetchDocuments,
    isFetching,
  } = useQuery<DocumentInfo[]>({
    queryKey: ['processing-documents'],
    queryFn: async () => {
      const res = await fetch(apiUrl('/api/v1/documents/'));
      if (!res.ok) throw new Error('Failed to fetch processing logs');
      const data: DocumentInfo[] = await res.json();
      data.sort((a, b) => (parseApiDate(b.created_at)?.getTime() || 0) - (parseApiDate(a.created_at)?.getTime() || 0));
      return data;
    },
    staleTime: 10000,
  });

  const error = queryError instanceof Error ? queryError.message : (queryError ? String(queryError) : null);

  // 2. Fetch Parsed JSON for selected document with React Query
  const {
    data: parsedData,
    isLoading: loadingParsed,
    error: parsedQueryError,
  } = useQuery({
    queryKey: ['parsed-document', selectedDocId],
    queryFn: async () => {
      if (!selectedDocId) return null;
      const res = await fetch(apiUrl(`/api/v1/documents/${selectedDocId}/parsed`));
      if (!res.ok) {
        let errMsg = `Failed to retrieve intermediate representation (HTTP ${res.status})`;
        try {
          const errData = await res.json();
          if (errData.detail) errMsg = errData.detail;
        } catch {}
        throw new Error(errMsg);
      }
      return res.json();
    },
    enabled: !!selectedDocId,
    staleTime: 60000,
  });

  const parsedError = parsedQueryError instanceof Error ? parsedQueryError.message : (parsedQueryError ? String(parsedQueryError) : null);

  const handleInspectJson = (docId: string) => {
    setSelectedDocId(docId);
  };

  const handleForceReprocess = async (docId: string) => {
    try {
      setReprocessingId(docId);
      const res = await fetch(apiUrl(`/api/v1/documents/${docId}/reprocess`), { method: 'POST' });
      if (!res.ok) throw new Error('Reprocess request failed');
      queryClient.invalidateQueries({ queryKey: ['processing-documents'] });
      queryClient.invalidateQueries({ queryKey: ['parsed-document', docId] });
      queryClient.invalidateQueries({ queryKey: ['overview-summary'] });
      queryClient.invalidateQueries({ queryKey: ['products-list'] });
      queryClient.invalidateQueries({ queryKey: ['reviews-list'] });
      queryClient.invalidateQueries({ queryKey: ['catalogHealth'] });
    } catch (err: any) {
      alert(`Error reprocessing: ${err?.message}`);
    } finally {
      setReprocessingId(null);
    }
  };

  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [clearError, setClearError] = useState<string | null>(null);

  const handleClearAll = async () => {
    if (!window.confirm('Are you sure you want to clear all processing logs? This will remove all document records and processing history. Products that were created will NOT be deleted.')) {
      return;
    }
    try {
      setClearing(true);
      setClearError(null);
      setSuccessMessage(null);
      const res = await fetch(apiUrl('/api/v1/documents/clear-all'), { method: 'DELETE' });
      if (!res.ok) {
        let errMsg = 'Failed to clear processing logs';
        try {
          const errData = await res.json();
          if (errData.detail) errMsg = errData.detail;
        } catch {}
        throw new Error(errMsg);
      }
      const data = await res.json();
      setSuccessMessage(data.message || `Processing history cleared — ${data.jobs_deleted ?? 0} jobs, ${data.documents_deleted ?? 0} documents, and ${data.steps_deleted ?? 0} steps removed.`);
      queryClient.setQueryData(['processing-documents'], []);
      queryClient.removeQueries({ queryKey: ['parsed-document'] });
      queryClient.invalidateQueries({ queryKey: ['processing-documents'] });
      queryClient.invalidateQueries({ queryKey: ['overview-summary'] });
      queryClient.invalidateQueries({ queryKey: ['catalogHealth'] });
      queryClient.invalidateQueries({ queryKey: ['products-list'] });
      setSelectedDocId(null);
    } catch (err: any) {
      setClearError(err?.message || 'Error clearing processing logs');
    } finally {
      setClearing(false);
    }
  };

  return (
    <div className="space-y-6 text-foreground rounded-none">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-2 border border-[#9B8F77]/30 bg-[#9B8F77]/5 px-3 py-1 text-[9px] uppercase tracking-widest font-medium text-[#9B8F77] mb-2">
            <FileText className="w-3.5 h-3.5" />
            Audit & Ingestion Stream
          </div>
          <h2 className="text-3xl font-serif font-normal tracking-tight">Processing Logs</h2>
          <p className="text-xs uppercase tracking-wider text-muted-foreground font-light mt-1">
            Monitor files, check parsing status logs, and inspect intermediate JSON documents.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleClearAll}
            disabled={clearing || documents.length === 0}
            className="h-10 px-4 border border-destructive/40 bg-card text-destructive hover:bg-destructive/10 text-xs uppercase tracking-widest font-medium transition rounded-none flex items-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {clearing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
            <span>Clear All</span>
          </button>
          <button 
            onClick={() => fetchDocuments()}
            className="h-10 px-4 border border-border bg-card text-muted-foreground hover:text-foreground text-xs uppercase tracking-widest font-medium transition rounded-none flex items-center gap-2"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-[#9B8F77] ${isFetching ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {successMessage && (
        <div className="bg-emerald-500/10 border border-emerald-500/30 text-emerald-500 text-xs rounded-none p-4 flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Activity className="w-4 h-4 flex-shrink-0" />
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

      {error && (
        <div className="bg-destructive/10 border border-destructive/20 text-destructive text-xs rounded-none p-4 flex items-center space-x-2">
          <AlertTriangle className="w-5 h-5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {loading ? (
        <div className="flex justify-center items-center py-20">
          <Loader2 className="w-8 h-8 text-primary animate-spin" />
        </div>
      ) : documents.length === 0 ? (
        <div className="bg-card border border-border rounded-none overflow-hidden">
          <div className="p-12 text-center text-muted-foreground flex flex-col items-center justify-center space-y-2">
            <Activity className="w-10 h-10 text-muted-foreground opacity-50" />
            <h4 className="font-serif text-lg font-normal text-foreground">No Processing History Yet</h4>
            <p className="text-xs uppercase tracking-wider max-w-xs font-light">Upload technical catalogs to run parser workers and monitor processes.</p>
          </div>
        </div>
      ) : (
        <div className="bg-card border border-border rounded-none shadow-sm overflow-hidden">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-background/50 border-b border-border text-[9px] font-medium text-muted-foreground uppercase tracking-widest">
                <th className="p-4">Document / File Details</th>
                <th className="p-4">Status</th>
                <th className="p-4">Page Count</th>
                <th className="p-4">Parser Details</th>
                <th className="p-4">Upload Date</th>
                <th className="p-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border text-xs">
              {documents.map((doc) => (
                <tr key={doc.id} className="hover:bg-accent/40 transition">
                  <td className="p-4">
                    <div className="flex items-center space-x-3">
                      <div className="w-9 h-9 border border-border bg-background flex items-center justify-center flex-shrink-0">
                        <FileText className="w-4 h-4 text-[#9B8F77]" />
                      </div>
                      <div>
                        <span className="font-medium block truncate max-w-xs text-foreground">{doc.filename}</span>
                        <span className="text-[10px] text-muted-foreground block font-mono">{(doc.file_size / (1024 * 1024)).toFixed(2)} MB • {doc.file_hash.substring(0, 12)}...</span>
                      </div>
                    </div>
                  </td>
                  <td className="p-4">
                    <span className={`px-2 py-0.5 text-[9px] uppercase tracking-widest font-mono border rounded-none ${
                      doc.status === 'processed' || doc.status === 'completed' ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-500' :
                      doc.status === 'failed' ? 'border-destructive/40 bg-destructive/10 text-destructive' :
                      'border-amber-500/40 bg-amber-500/10 text-amber-500 animate-pulse'
                    }`}>
                      {doc.status}
                    </span>
                  </td>
                  <td className="p-4 font-mono">
                    {doc.page_count !== null ? `${doc.page_count} pages` : 'N/A'}
                  </td>
                  <td className="p-4 font-mono text-[10px]">
                    {doc.parser_name ? (
                      <span>{doc.parser_name} v{doc.parser_version}</span>
                    ) : (
                      <span className="text-muted-foreground">-</span>
                    )}
                  </td>
                  <td className="p-4 text-[10px] font-mono text-muted-foreground">
                    {formatApiDateTime(doc.created_at)}
                  </td>
                  <td className="p-4 text-right">
                    <div className="flex justify-end space-x-2">
                      <button 
                        onClick={() => handleForceReprocess(doc.id)}
                        disabled={reprocessingId === doc.id}
                        title="Force reprocess"
                        className="p-1.5 border border-border bg-background hover:bg-card text-muted-foreground hover:text-foreground transition rounded-none disabled:opacity-50"
                      >
                        <RefreshCw className={`w-3.5 h-3.5 ${reprocessingId === doc.id ? 'animate-spin text-[#9B8F77]' : ''}`} />
                      </button>
                      
                      {(doc.status === 'processed' || doc.status === 'completed') && (
                        <button 
                          onClick={() => handleInspectJson(doc.id)}
                          title="Inspect intermediate JSON"
                          className="p-1.5 border border-border bg-background hover:bg-card text-[#9B8F77] hover:text-foreground transition rounded-none"
                        >
                          <Eye className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* JSON Viewer Sidebar Modal */}
      {selectedDocId && (
        <div className="fixed inset-0 bg-background/80 backdrop-blur-sm z-50 flex justify-end">
          <div className="w-full max-w-2xl bg-card border-l border-border h-full flex flex-col shadow-2xl p-6 space-y-4 rounded-none">
            <div className="flex justify-between items-center border-b border-border pb-4">
              <div>
                <h4 className="font-serif text-lg font-normal text-foreground">Intermediate JSON Viewer</h4>
                <p className="text-[10px] font-mono text-muted-foreground mt-0.5">Doc ID: {selectedDocId}</p>
              </div>
              <button 
                onClick={() => setSelectedDocId(null)}
                className="px-3 py-1.5 border border-border text-xs uppercase tracking-widest hover:bg-muted font-medium transition rounded-none"
              >
                Close Panel
              </button>
            </div>

            {loadingParsed ? (
              <div className="flex-1 flex justify-center items-center">
                <Loader2 className="w-8 h-8 text-primary animate-spin" />
              </div>
            ) : parsedError ? (
              <div className="flex-1 flex flex-col justify-center items-center p-6 text-center space-y-4">
                <div className="p-4 bg-destructive/10 border border-destructive/20 text-destructive text-xs max-w-md w-full text-left">
                  <p className="font-semibold uppercase tracking-wider mb-1">Failed to Retrieve Intermediate Representation</p>
                  <p className="font-mono text-[11px] leading-relaxed break-words">{parsedError}</p>
                </div>
                {selectedDocId && (
                  <button
                    onClick={() => {
                      const id = selectedDocId;
                      setSelectedDocId(null);
                      handleForceReprocess(id);
                    }}
                    className="px-4 py-2 bg-primary text-primary-foreground text-xs uppercase tracking-widest font-medium hover:bg-primary/90 transition rounded-none"
                  >
                    Force Reprocess Document
                  </button>
                )}
              </div>
            ) : parsedData ? (
              <div className="flex-1 flex flex-col space-y-4 overflow-hidden">
                <div className="grid grid-cols-2 gap-4 text-xs bg-background p-4 border border-border rounded-none">
                  <div>
                    <span className="text-[9px] uppercase tracking-widest text-muted-foreground block">Content Hash</span>
                    <span className="font-semibold text-foreground truncate block font-mono">{parsedData.content_hash}</span>
                  </div>
                  <div>
                    <span className="text-[9px] uppercase tracking-widest text-muted-foreground block">Parser Engine</span>
                    <span className="font-semibold text-foreground block font-mono">{parsedData.parser?.name} v{parsedData.parser?.version}</span>
                  </div>
                </div>

                <div className="flex-1 bg-background border border-border p-4 rounded-none overflow-y-auto text-xs font-mono">
                  <pre>{JSON.stringify(parsedData, null, 2)}</pre>
                </div>
              </div>
            ) : (
              <div className="text-center text-muted-foreground py-20 text-xs uppercase tracking-wider">
                No layout representation available.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
