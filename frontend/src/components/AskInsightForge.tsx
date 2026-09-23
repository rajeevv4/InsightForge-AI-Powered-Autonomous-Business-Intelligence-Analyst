import React, { useState } from 'react';
import {
  Sparkles,
  Send,
  HelpCircle,
  CheckCircle2,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  AlertCircle
} from 'lucide-react';
import { api } from '../services/api';
import { AskAIResponse } from '../types/api';

const EXAMPLE_QUESTIONS = [
  "Which category generated the highest revenue?",
  "What is our average order value?",
  "Which state has the highest sales?",
  "How is our delivery performance?",
  "Which payment method is most common?",
  "Give me a summary of our key business metrics."
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
        'Failed to process your question. Please ensure the server is active.'
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

  // Safe inline text renderer for **bold** markers
  const renderFormattedText = (text: string) => {
    const parts = text.split(/(\*\*.*?\*\*)/g);
    return parts.map((part, index) => {
      if (part.startsWith('**') && part.endsWith('**')) {
        return (
          <strong key={index} className="font-bold text-slate-900">
            {part.slice(2, -2)}
          </strong>
        );
      }
      return part;
    });
  };

  return (
    <div className="bg-white border border-slate-200/80 rounded-2xl p-6 shadow-xs transition-all">
      {/* Search Input Box */}
      <div className="relative mb-4">
        <div className="flex gap-2">
          <div className="relative flex-1">
            <input
              type="text"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="What would you like to know about your business?"
              disabled={loading}
              className="w-full bg-slate-50 border border-slate-200 rounded-xl pl-4 pr-10 py-3.5 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-500 transition-all disabled:opacity-50"
            />
            {question && (
              <button
                onClick={() => setQuestion('')}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 text-xs font-bold"
              >
                ✕
              </button>
            )}
          </div>

          <button
            onClick={() => handleAsk()}
            disabled={loading || !question.trim()}
            className="flex items-center space-x-2 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-xs px-5 py-3.5 rounded-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-xs active:scale-98"
          >
            {loading ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                <span>Analyzing...</span>
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4" />
                <span>Ask AI</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Example Prompt Pills */}
      <div className="mb-6">
        <div className="flex items-center space-x-1.5 text-xs text-slate-500 mb-2 font-medium">
          <HelpCircle className="w-3.5 h-3.5 text-indigo-500" />
          <span>Try asking these example prompts:</span>
        </div>
        <div className="flex flex-wrap gap-2">
          {EXAMPLE_QUESTIONS.map((q, idx) => (
            <button
              key={idx}
              onClick={() => handleAsk(q)}
              disabled={loading}
              className="text-xs bg-slate-100/80 hover:bg-indigo-50 text-slate-700 hover:text-indigo-600 border border-slate-200/80 hover:border-indigo-200 rounded-lg px-3 py-1.5 transition-all text-left disabled:opacity-50 font-medium"
            >
              "{q}"
            </button>
          ))}
        </div>
      </div>

      {/* Error Message */}
      {error && (
        <div className="mb-6 bg-rose-50 border border-rose-200 rounded-xl p-4 flex items-start space-x-3 text-rose-800 text-xs">
          <AlertCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
          <div className="flex-1">{error}</div>
        </div>
      )}

      {/* Loading State */}
      {loading && (
        <div className="bg-slate-50 border border-slate-200/80 rounded-xl p-6 animate-pulse space-y-3">
          <div className="h-4 bg-slate-200 rounded w-1/4"></div>
          <div className="h-3 bg-slate-200 rounded w-full"></div>
          <div className="h-3 bg-slate-200 rounded w-5/6"></div>
        </div>
      )}

      {/* Business Insight Result Card */}
      {response && !loading && (
        <div className="bg-slate-50/70 border border-slate-200/80 rounded-xl overflow-hidden shadow-xs transition-all">
          {/* Subtle Metadata Bar */}
          <div className="bg-white border-b border-slate-200/80 px-5 py-2.5 flex items-center justify-between text-xs">
            <div className="flex items-center space-x-2 text-slate-500 font-medium">
              <span>Question:</span>
              <span className="text-slate-900 font-semibold">"{response.question}"</span>
            </div>

            <span className="text-[11px] bg-indigo-50 text-indigo-700 border border-indigo-100 px-2.5 py-0.5 rounded-full font-medium">
              Powered by AI
            </span>
          </div>

          {/* AI Grounded Answer Body */}
          <div className="p-5 space-y-4 text-slate-800">
            <div className="text-sm leading-relaxed text-slate-800 space-y-2">
              {response.answer.split('\n').map((line, idx) => {
                if (!line.trim()) return <div key={idx} className="h-1" />;
                return (
                  <p key={idx} className="mb-1.5 last:mb-0">
                    {renderFormattedText(line)}
                  </p>
                );
              })}
            </div>

            {/* Expandable Evidence View */}
            {response.evidence && (
              <div className="pt-3 border-t border-slate-200/80">
                <button
                  onClick={() => setShowEvidence(!showEvidence)}
                  className="flex items-center justify-between w-full text-xs font-semibold text-slate-500 hover:text-indigo-600 transition-colors py-1"
                >
                  <span className="flex items-center space-x-2">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                    <span>View Grounding Data ({response.evidence.metric})</span>
                  </span>
                  {showEvidence ? (
                    <ChevronUp className="w-4 h-4" />
                  ) : (
                    <ChevronDown className="w-4 h-4" />
                  )}
                </button>

                {showEvidence && (
                  <div className="mt-2 bg-white border border-slate-200/80 rounded-lg p-3 text-xs font-mono overflow-x-auto text-slate-700 max-h-56">
                    <div className="text-slate-400 mb-1">// Data provenance: {response.evidence.source}</div>
                    <pre className="text-slate-800">
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
