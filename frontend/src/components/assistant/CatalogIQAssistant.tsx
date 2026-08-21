import React, { useState, useEffect, useRef } from 'react';
import { X, Send, Loader2, Sparkles, RefreshCw, AlertCircle, MessageSquare } from 'lucide-react';
import { useLocation } from 'react-router-dom';

interface ChatTurn {
  role: 'user' | 'assistant';
  content: string;
  suggestions?: string[];
}

export const CatalogIQAssistant: React.FC = () => {
  const location = useLocation();
  const [isOpen, setIsOpen] = useState<boolean>(false);
  const [inputMessage, setInputMessage] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatTurn[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Determine current page context based on path
  const getPageContext = () => {
    const path = location.pathname;
    if (path.startsWith('/search')) return { page: 'search' };
    if (path.startsWith('/upload')) return { page: 'upload' };
    if (path.startsWith('/jobs')) return { page: 'jobs' };
    if (path.startsWith('/products/')) return { page: 'product_detail', product_id: path.split('/')[2] };
    if (path.startsWith('/products') || path.startsWith('/catalog')) return { page: 'products' };
    if (path.startsWith('/reviews')) return { page: 'reviews' };
    if (path.startsWith('/health')) return { page: 'health' };
    return { page: 'dashboard' };
  };

  // Get initial contextual suggested questions
  const getInitialSuggestions = (): string[] => {
    const ctx = getPageContext();
    if (ctx.page === 'upload') {
      return [
        'If I upload an Excel file, what happens?',
        'What file formats are supported?',
        'How does batch processing work?',
        'Can I upload a ZIP archive?',
      ];
    }
    if (ctx.page === 'search') {
      return [
        'How does hybrid search work?',
        'What is the difference between semantic and keyword search?',
        'How does exact SKU match boost ranking?',
      ];
    }
    if (ctx.page === 'reviews') {
      return [
        'What does needs_review mean?',
        'Why does a product need review?',
        'How do I resolve multi-source conflicts?',
      ];
    }
    return [
      'What file formats are supported?',
      'If I upload an Excel file, what happens?',
      'How does batch processing work?',
      'What does needs_review mean?',
    ];
  };

  // Scroll to bottom when messages update
  useEffect(() => {
    if (isOpen) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, loading, isOpen]);

  const handleSendMessage = async (textToSend?: string) => {
    const msg = (textToSend !== undefined ? textToSend : inputMessage).trim();
    if (!msg || loading) return;

    const userTurn: ChatTurn = { role: 'user', content: msg };
    const updatedMessages = [...messages, userTurn];
    setMessages(updatedMessages);
    setInputMessage('');
    setLoading(true);
    setError(null);

    const historyPayload = updatedMessages.map((m) => ({
      role: m.role,
      content: m.content,
    }));

    try {
      const response = await fetch('/api/v1/assistant/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: msg,
          history: historyPayload,
          context: getPageContext(),
        }),
      });

      if (!response.ok) {
        throw new Error(`Assistant query failed with HTTP ${response.status}`);
      }

      const data = await response.json();
      const assistantTurn: ChatTurn = {
        role: 'assistant',
        content:
          data.message ||
          data.reply ||
          (data.detail ? `Assistant Notice: ${data.detail}` : 'CatalogIQ Assistant is ready to help.'),
        suggestions: data.suggestions || [],
      };

      setMessages((prev) => [...prev, assistantTurn]);
    } catch (err: any) {
      console.error('Assistant error:', err);
      setError(err?.message || 'Failed to connect to CatalogIQ Assistant');
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  // Get active suggestions
  const lastAssistantTurn = [...messages].reverse().find((m) => m.role === 'assistant');
  const currentSuggestions = lastAssistantTurn?.suggestions && lastAssistantTurn.suggestions.length > 0
    ? lastAssistantTurn.suggestions
    : (messages.length === 0 ? getInitialSuggestions() : []);

  return (
    <div className="fixed bottom-6 right-6 z-50 select-none">
      {/* Assistant Floating Button */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className="h-11 px-4 border border-foreground bg-foreground text-background hover:bg-transparent hover:text-foreground text-[10px] uppercase tracking-widest font-semibold transition duration-150 rounded-none shadow-xl flex items-center gap-2"
          title="Open CatalogIQ Assistant"
        >
          <Sparkles className="w-4 h-4 text-[#9B8F77]" />
          <span className="hidden sm:inline">CatalogIQ Assistant</span>
        </button>
      )}

      {/* Assistant Chat Panel */}
      {isOpen && (
        <div className="bg-card border border-border rounded-none shadow-2xl w-full max-w-sm sm:max-w-md h-[520px] flex flex-col overflow-hidden text-foreground">
          {/* Header */}
          <div className="bg-background border-b border-border px-4 py-3 flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="p-1.5 border border-border bg-card text-[#9B8F77] rounded-none">
                <Sparkles className="w-4 h-4" />
              </div>
              <div>
                <h4 className="text-base font-serif font-normal text-foreground leading-tight">CatalogIQ Assistant</h4>
                <p className="text-[9px] uppercase tracking-widest text-muted-foreground font-light">In-Product Intelligence</p>
              </div>
            </div>
            <button
              onClick={() => setIsOpen(false)}
              className="p-1.5 text-muted-foreground hover:text-foreground transition"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Messages Scroll Body */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4 text-xs font-light">
            {/* Welcome Greeting */}
            {messages.length === 0 && (
              <div className="border border-border bg-background p-4 space-y-2 rounded-none">
                <div className="flex items-center gap-2 text-[#9B8F77] font-medium text-xs">
                  <MessageSquare className="w-3.5 h-3.5" />
                  <span className="uppercase tracking-widest text-[10px]">Welcome to CatalogIQ Assistant</span>
                </div>
                <p className="text-muted-foreground text-xs leading-relaxed font-light">
                  Ask me anything about multi-format document parsing, attribute extraction, confidence scoring, quality validation, multi-source reconciliation, or hybrid search.
                </p>
              </div>
            )}

            {/* Render Chat Messages */}
            {messages.map((turn, idx) => (
              <div
                key={idx}
                className={`flex flex-col ${turn.role === 'user' ? 'items-end' : 'items-start'}`}
              >
                <div
                  className={`max-w-[88%] p-3 leading-relaxed text-xs rounded-none ${
                    turn.role === 'user'
                      ? 'bg-foreground text-background font-medium'
                      : 'bg-background border border-border text-foreground font-light whitespace-pre-wrap'
                  }`}
                >
                  {turn.content}
                </div>
              </div>
            ))}

            {/* Loading Indicator */}
            {loading && (
              <div className="flex items-center gap-2 text-muted-foreground text-xs bg-background p-2.5 border border-border w-fit rounded-none font-mono">
                <Loader2 className="w-3.5 h-3.5 animate-spin text-[#9B8F77]" />
                <span>Consulting knowledge base...</span>
              </div>
            )}

            {/* Error Message */}
            {error && (
              <div className="border border-destructive/40 bg-destructive/10 p-3 text-destructive flex items-start justify-between gap-2 rounded-none">
                <div className="flex items-start gap-2 text-xs">
                  <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                  <span>{error}</span>
                </div>
                <button
                  onClick={() => handleSendMessage()}
                  className="text-xs bg-destructive text-destructive-foreground px-2 py-1 transition flex items-center gap-1 shrink-0 rounded-none uppercase font-mono"
                >
                  <RefreshCw className="w-3 h-3" /> Retry
                </button>
              </div>
            )}

            {/* Contextual Suggested Questions Chips */}
            {!loading && currentSuggestions.length > 0 && (
              <div className="pt-2 space-y-1.5">
                <span className="text-[9px] font-medium uppercase tracking-widest text-muted-foreground">Suggested Questions:</span>
                <div className="flex flex-wrap gap-1.5">
                  {currentSuggestions.map((sug, i) => (
                    <button
                      key={i}
                      onClick={() => handleSendMessage(sug)}
                      className="bg-background hover:bg-accent border border-border text-muted-foreground hover:text-foreground text-[10px] px-2.5 py-1 transition text-left leading-tight rounded-none"
                    >
                      {sug}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Footer Input Bar */}
          <div className="bg-background border-t border-border p-3">
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={inputMessage}
                onChange={(e) => setInputMessage(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask about CatalogIQ features or specifications..."
                className="flex-1 bg-card border border-border text-foreground px-3 py-2 text-xs focus:outline-none focus:border-foreground rounded-none font-light"
              />
              <button
                onClick={() => handleSendMessage()}
                disabled={loading || !inputMessage.trim()}
                className="h-8 px-3 bg-foreground text-background border border-foreground hover:bg-transparent hover:text-foreground transition disabled:opacity-40 disabled:cursor-not-allowed rounded-none"
                title="Send Message"
              >
                <Send className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
