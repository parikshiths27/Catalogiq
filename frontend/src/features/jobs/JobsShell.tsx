import React, { useState, useEffect } from 'react';
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
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [clearing, setClearing] = useState(false);

  // JSON Inspector Modal state
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [parsedData, setParsedData] = useState<any | null>(null);
  const [loadingParsed, setLoadingParsed] = useState(false);

  const fetchDocuments = async () => {
    try {
      setLoading(true);
      const res = await fetch(apiUrl('/api/v1/documents/'));
      if (!res.ok) throw new Error('Failed to fetch documents list');
      const data: DocumentInfo[] = await res.json();
      // Sort by created_at desc
      data.sort((a, b) => (parseApiDate(b.created_at)?.getTime() || 0) - (parseApiDate(a.created_at)?.getTime() || 0));
      setDocuments(data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDocuments();
  }, []);

  const handleInspectJson = async (docId: string) => {
    setSelectedDocId(docId);
    setParsedData(null);
    setLoadingParsed(true);
    try {
      const res = await fetch(apiUrl(`/api/v1/documents/${docId}/parsed`));
      if (!res.ok) throw new Error('Failed to retrieve intermediate representation');
      const data = await res.json();
      setParsedData(data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoadingParsed(false);
    }
  };

  const handleForceReprocess = async (docId: string) => {
    try {
      const res = await fetch(apiUrl(`/api/v1/documents/${docId}/reprocess`), { method: 'POST' });
      if (!res.ok) throw new Error('Reprocess request failed');
      // Refresh documents list
      fetchDocuments();
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleClearAll = async () => {
    if (!window.confirm('Are you sure you want to clear all processing logs? This will remove all document records and processing history. Products that were created will NOT be deleted.')) {
      return;
    }
    try {
      setClearing(true);
      const res = await fetch(apiUrl('/api/v1/documents/clear-all'), { method: 'DELETE' });
      if (!res.ok) throw new Error('Failed to clear processing logs');
      setDocuments([]);
      setError(null);
    } catch (err: any) {
      setError(err.message);
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
            onClick={fetchDocuments}
            className="h-10 px-4 border border-border bg-card text-muted-foreground hover:text-foreground text-xs uppercase tracking-widest font-medium transition rounded-none flex items-center gap-2"
          >
            <RefreshCw className="w-4 h-4 text-[#9B8F77]" />
            <span>Refresh</span>
          </button>
        </div>
      </div>

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
            <h4 className="font-serif text-lg font-normal text-foreground">No Documents Ingested</h4>
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
                        title="Force reprocess"
                        className="p-1.5 border border-border bg-background hover:bg-card text-muted-foreground hover:text-foreground transition rounded-none"
                      >
                        <RefreshCw className="w-3.5 h-3.5" />
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
                Failed to parse layout representation.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
