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
    if (path.startsWith('/products')) return { page: 'products' };
    if (path.startsWith('/reviews')) return { page: 'reviews' };
    if (path.startsWith('/health')) return { page: 'health' };
    return { page: 'dashboard' };
  };

  // Get initial contextual suggested questions
  const getInitialSuggestions = (): string[] => {
    const ctx = getPageContext();
    if (ctx.page === 'upload') {
      return [
        'How do I upload a product catalog?',
        'What happens after document parsing?',
        'Why is my document still processing?',
      ];
    }
    if (ctx.page === 'search') {
      return [
        'What is the difference between semantic and keyword search?',
        'What does the relevance score mean?',
        'How does hybrid search rank exact SKU matches?',
      ];
    }
    if (ctx.page === 'reviews') {
      return [
        'Why does a product need review?',
        'How do I resolve multi-source conflicts?',
        'What is evidence verification?',
      ];
    }
    if (ctx.page === 'product_detail') {
      return [
        'How is the quality score calculated?',
        'What is the evidence for attributes?',
        'How does commerce enrichment work?',
      ];
    }
    return [
      'How does CatalogIQ work?',
      'How do I upload a technical catalog?',
      'What does product quality score mean?',
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
        const errJson = await response.json().catch(() => ({}));
        throw new Error(errJson.detail || `Assistant request failed (${response.status})`);
      }

      const data = await response.json();
      const assistantTurn: ChatTurn = {
        role: 'assistant',
        content: data.message || 'CatalogIQ Assistant response received.',
        suggestions: data.suggestions || [],
      };
      setMessages((prev) => [...prev, assistantTurn]);
    } catch (err: any) {
      console.error('Assistant API error:', err);
      setError('CatalogIQ Assistant is temporarily unavailable. You can continue using CatalogIQ normally.');
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

  const currentSuggestions =
    messages.length > 0 && messages[messages.length - 1].role === 'assistant'
      ? messages[messages.length - 1].suggestions || []
      : getInitialSuggestions();

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col items-end">
      {/* Floating Toggle Button */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className="bg-indigo-600 hover:bg-indigo-500 text-white p-3.5 rounded-full shadow-2xl transition-all transform hover:scale-105 flex items-center gap-2 border border-indigo-400/30 group"
          title="CatalogIQ Assistant / Help Center"
        >
          <Sparkles className="w-5 h-5 text-amber-300 animate-pulse" />
          <span className="text-xs font-semibold pr-1 hidden sm:inline">CatalogIQ Assistant</span>
        </button>
      )}

      {/* Assistant Chat Panel */}
      {isOpen && (
        <div className="bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl w-full max-w-sm sm:max-w-md h-[520px] flex flex-col overflow-hidden text-slate-100 animate-in fade-in slide-in-from-bottom-5 duration-200">
          {/* Header */}
          <div className="bg-slate-950 border-b border-slate-800 px-4 py-3 flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="p-1.5 bg-indigo-950/80 border border-indigo-700/50 rounded-lg text-indigo-400">
                <Sparkles className="w-4 h-4 text-amber-400" />
              </div>
              <div>
                <h4 className="text-sm font-bold text-white leading-tight">CatalogIQ Assistant</h4>
                <p className="text-[11px] text-slate-400">In-Product Help & Documentation</p>
              </div>
            </div>
            <button
              onClick={() => setIsOpen(false)}
              className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Messages Scroll Body */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4 text-xs">
            {/* Welcome Greeting */}
            {messages.length === 0 && (
              <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-4 space-y-2">
                <div className="flex items-center gap-2 text-indigo-400 font-semibold text-xs">
                  <MessageSquare className="w-4 h-4" />
                  <span>Welcome to CatalogIQ Help</span>
                </div>
                <p className="text-slate-300 text-xs leading-relaxed">
                  Hi! I'm your CatalogIQ Assistant. Ask me anything about document parsing, attribute extraction, confidence scoring, quality validation, multi-source reconciliation, or hybrid search.
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
                  className={`max-w-[88%] rounded-xl px-3.5 py-2.5 leading-relaxed text-xs ${
                    turn.role === 'user'
                      ? 'bg-indigo-600 text-white rounded-br-none shadow'
                      : 'bg-slate-950 border border-slate-800 text-slate-200 rounded-bl-none shadow-inner whitespace-pre-wrap'
                  }`}
                >
                  {turn.content}
                </div>
              </div>
            ))}

            {/* Loading Indicator */}
            {loading && (
              <div className="flex items-center gap-2 text-slate-400 text-xs bg-slate-950/40 p-2.5 rounded-lg border border-slate-800/50 w-fit">
                <Loader2 className="w-3.5 h-3.5 animate-spin text-indigo-400" />
                <span>Consulting CatalogIQ knowledge...</span>
              </div>
            )}

            {/* Error Message & Retry */}
            {error && (
              <div className="bg-red-950/50 border border-red-800/80 rounded-xl p-3 text-red-300 flex items-start justify-between gap-2">
                <div className="flex items-start gap-2 text-xs">
                  <AlertCircle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
                  <span>{error}</span>
                </div>
                <button
                  onClick={() => handleSendMessage()}
                  className="text-xs bg-red-900/60 hover:bg-red-800 px-2 py-1 rounded text-white transition flex items-center gap-1 shrink-0"
                >
                  <RefreshCw className="w-3 h-3" /> Retry
                </button>
              </div>
            )}

            {/* Contextual Suggested Questions Chips */}
            {!loading && currentSuggestions.length > 0 && (
              <div className="pt-2 space-y-1.5">
                <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Suggested Questions:</span>
                <div className="flex flex-wrap gap-1.5">
                  {currentSuggestions.map((sug, i) => (
                    <button
                      key={i}
                      onClick={() => handleSendMessage(sug)}
                      className="bg-slate-950 hover:bg-indigo-950 border border-slate-800 hover:border-indigo-700 text-indigo-300 hover:text-indigo-200 text-[11px] px-2.5 py-1 rounded-lg transition text-left leading-tight"
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
          <div className="bg-slate-950 border-t border-slate-800 p-3">
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={inputMessage}
                onChange={(e) => setInputMessage(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask about CatalogIQ features, stages, or errors..."
                className="flex-1 bg-slate-900 border border-slate-700/80 text-white rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
              />
              <button
                onClick={() => handleSendMessage()}
                disabled={loading || !inputMessage.trim()}
                className="bg-indigo-600 hover:bg-indigo-500 text-white p-2 rounded-lg transition disabled:opacity-40 disabled:cursor-not-allowed"
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
