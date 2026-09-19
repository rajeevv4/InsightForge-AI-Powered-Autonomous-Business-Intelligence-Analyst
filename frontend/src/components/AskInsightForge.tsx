import React, { useState } from 'react';
import {
  Sparkles,
  Send,
  Bot,
  Database,
  AlertCircle,
  ChevronDown,
  ChevronUp,
  HelpCircle,
  CheckCircle2,
  RefreshCw,
  ShieldCheck
} from 'lucide-react';
import { api } from '../services/api';
import { AskAIResponse } from '../types/api';

const EXAMPLE_QUESTIONS = [
  "Which category generated the highest revenue?",
  "What is our average order value?",
  "Which state has the highest sales?",
  "How is our delivery performance?",
  "Which payment method is most common?",
  "Give me a summary of our current KPIs."
];

export const AskInsightForge: React.FC = () => {
  const [question, setQuestion] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<AskAIResponse | null>(null);
  const [showEvidence, setShowEvidence] = useState<boolean>(false);

  const handleAsk = async (queryToAsk?: string) => {
    const targetQuestion = (queryToAsk !== undefined ? queryToAsk : question).trim();
    if (!targetQuestion) return;

    setQuestion(targetQuestion);
    setLoading(true);
    setError(null);
    setShowEvidence(false);

    try {
      const result = await api.askAI(targetQuestion);
      setResponse(result);
    } catch (err: any) {
      console.error('Failed to query Ask InsightForge AI:', err);
      setError(
        err?.response?.data?.detail ||
        'Failed to process your business question. Please ensure the backend is running.'
      );
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !loading) {
      handleAsk();
    }
  };

  // Safe inline formatter for **bold** text without using dangerouslySetInnerHTML
  const renderFormattedText = (text: string) => {
    const parts = text.split(/(\*\*.*?\*\*)/g);
    return parts.map((part, index) => {
      if (part.startsWith('**') && part.endsWith('**')) {
        return (
          <strong key={index} className="font-semibold text-cyan-300">
            {part.slice(2, -2)}
          </strong>
        );
      }
      return part;
    });
  };

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl backdrop-blur-sm transition-all">
      {/* Header Section */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
        <div className="flex items-center space-x-3">
          <div className="p-2.5 bg-gradient-to-tr from-cyan-500/20 to-blue-500/20 border border-cyan-500/30 rounded-xl text-cyan-400 shadow-inner">
            <Sparkles className="w-6 h-6 animate-pulse" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
              Ask InsightForge
              <span className="text-[11px] bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 px-2.5 py-0.5 rounded-full font-medium">
                Powered by Gemini 2.5 Flash
              </span>
            </h2>
            <p className="text-xs text-slate-400 mt-0.5 flex items-center gap-1.5">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
              Grounded in validated PostgreSQL analytics
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-2 text-xs text-slate-400 bg-slate-950/60 border border-slate-800 px-3 py-1.5 rounded-lg font-mono">
          <Database className="w-3.5 h-3.5 text-emerald-400" />
          <span>No Direct SQL Access</span>
        </div>
      </div>

      {/* Input Form */}
      <div className="relative mb-4">
        <div className="flex gap-2">
          <div className="relative flex-1">
            <input
              type="text"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask a natural language business question... (e.g. Which category generated highest revenue?)"
              disabled={loading}
              className="w-full bg-slate-950/80 border border-slate-700/80 rounded-xl pl-4 pr-10 py-3 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-cyan-500 focus:border-transparent transition-all disabled:opacity-50"
            />
            {question && (
              <button
                onClick={() => setQuestion('')}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 text-xs font-bold"
              >
                ✕
              </button>
            )}
          </div>

          <button
            onClick={() => handleAsk()}
            disabled={loading || !question.trim()}
            className="flex items-center space-x-2 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white font-semibold text-sm px-5 py-3 rounded-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-cyan-900/20 active:scale-95"
          >
            {loading ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                <span>Analyzing...</span>
              </>
            ) : (
              <>
                <Send className="w-4 h-4" />
                <span>Ask AI</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Example Question Pills */}
      <div className="mb-6">
        <div className="flex items-center space-x-1.5 text-xs text-slate-400 mb-2 font-medium">
          <HelpCircle className="w-3.5 h-3.5 text-cyan-400" />
          <span>Try asking these example business questions:</span>
        </div>
        <div className="flex flex-wrap gap-2">
          {EXAMPLE_QUESTIONS.map((q, idx) => (
            <button
              key={idx}
              onClick={() => handleAsk(q)}
              disabled={loading}
              className="text-xs bg-slate-950/70 hover:bg-slate-800 text-slate-300 border border-slate-800 hover:border-cyan-500/40 rounded-lg px-3 py-1.5 transition-all text-left disabled:opacity-50"
            >
              "{q}"
            </button>
          ))}
        </div>
      </div>

      {/* Error Message */}
      {error && (
        <div className="mb-6 bg-red-950/40 border border-red-800/60 rounded-xl p-4 flex items-start space-x-3 text-red-300 text-sm">
          <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
          <div className="flex-1">{error}</div>
        </div>
      )}

      {/* Loading Skeleton */}
      {loading && (
        <div className="bg-slate-950/60 border border-slate-800/80 rounded-xl p-6 animate-pulse space-y-4">
          <div className="flex items-center space-x-3">
            <div className="w-8 h-8 bg-slate-800 rounded-lg"></div>
            <div className="h-4 bg-slate-800 rounded w-1/3"></div>
          </div>
          <div className="h-3 bg-slate-800 rounded w-full"></div>
          <div className="h-3 bg-slate-800 rounded w-5/6"></div>
          <div className="h-3 bg-slate-800 rounded w-2/3"></div>
        </div>
      )}

      {/* Response Box */}
      {response && !loading && (
        <div className="bg-slate-950/90 border border-slate-800 rounded-xl overflow-hidden shadow-2xl transition-all">
          {/* Response Metadata Bar */}
          <div className="bg-slate-900/80 border-b border-slate-800/80 px-5 py-3 flex flex-wrap items-center justify-between gap-2 text-xs">
            <div className="flex items-center space-x-2">
              <Bot className="w-4 h-4 text-cyan-400" />
              <span className="text-slate-400 font-medium">Intent Match:</span>
              <span className="font-mono bg-cyan-500/10 text-cyan-300 border border-cyan-500/30 px-2 py-0.5 rounded font-semibold">
                {response.intent}
              </span>
            </div>

            <div className="flex items-center space-x-3">
              <div className="flex items-center space-x-1">
                <span className="text-slate-400 font-medium">Classification Confidence:</span>
                <span className={`font-mono px-2 py-0.5 rounded font-bold ${
                  response.confidence >= 0.8
                    ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
                    : response.confidence >= 0.6
                    ? 'bg-amber-500/10 text-amber-400 border border-amber-500/30'
                    : 'bg-red-500/10 text-red-400 border border-red-500/30'
                }`}>
                  {(response.confidence * 100).toFixed(0)}%
                </span>
              </div>
            </div>
          </div>

          {/* AI Grounded Explanation Body */}
          <div className="p-5 space-y-4 text-slate-200">
            <div className="text-xs text-slate-400 font-medium italic border-l-2 border-cyan-500/50 pl-3">
              Q: "{response.question}"
            </div>

            <div className="prose prose-invert max-w-none text-sm leading-relaxed bg-slate-900/40 p-4 rounded-xl border border-slate-800/50">
              {response.answer.split('\n').map((line, idx) => {
                if (!line.trim()) return <div key={idx} className="h-2" />;
                return (
                  <p key={idx} className="mb-2 last:mb-0">
                    {renderFormattedText(line)}
                  </p>
                );
              })}
            </div>

            {/* Evidence Expander Toggle */}
            {response.evidence && (
              <div className="pt-2 border-t border-slate-800/60">
                <button
                  onClick={() => setShowEvidence(!showEvidence)}
                  className="flex items-center justify-between w-full text-xs font-semibold text-slate-400 hover:text-cyan-400 transition-colors py-1.5"
                >
                  <span className="flex items-center space-x-2">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                    <span>Grounded Analytics Evidence ({response.evidence.metric})</span>
                  </span>
                  {showEvidence ? (
                    <ChevronUp className="w-4 h-4 text-slate-400" />
                  ) : (
                    <ChevronDown className="w-4 h-4 text-slate-400" />
                  )}
                </button>

                {showEvidence && (
                  <div className="mt-3 bg-slate-950 border border-slate-800 rounded-lg p-3 text-xs font-mono overflow-x-auto text-slate-300 max-h-60">
                    <div className="text-slate-500 mb-1">// Source: {response.evidence.source}</div>
                    <pre className="text-slate-300">
                      {JSON.stringify(response.evidence.data, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
