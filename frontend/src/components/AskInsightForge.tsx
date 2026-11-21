import React, { useState } from 'react';
import {
  Sparkles,
  HelpCircle,
  CheckCircle2,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  Database,
  Table as TableIcon,
  BarChart2,
  TrendingUp,
  Code
} from 'lucide-react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid
} from 'recharts';
import { api } from '../services/api';
import { SQLAskResponse } from '../types/api';
import { ErrorBanner } from './ErrorBanner';

const EXAMPLE_QUESTIONS = [
  "Which category generated the highest revenue?",
  "What is our average order value?",
  "Which customer states generated the most sales in 2017?",
  "How is our on-time delivery performance?",
  "Top 5 sellers by fulfilled orders?",
  "Show monthly gross revenue trend for 2018."
];

export const AskInsightForge: React.FC = () => {
  const [question, setQuestion] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [isDbUnavailable, setIsDbUnavailable] = useState<boolean>(false);
  const [response, setResponse] = useState<SQLAskResponse | null>(null);
  const [showSql, setShowSql] = useState<boolean>(false);
  const [showTable, setShowTable] = useState<boolean>(true);

  const handleAsk = async (queryToAsk?: string) => {
    const targetQuestion = (queryToAsk !== undefined ? queryToAsk : question).trim();
    if (!targetQuestion) return;

    setQuestion(targetQuestion);
    setLoading(true);
    setError(null);
    setIsDbUnavailable(false);
    setShowSql(false);

    try {
      const result = await api.sqlAskAI(targetQuestion);
      setResponse(result);
    } catch (err: any) {
      console.error('Failed to query Ask InsightForge AI:', err);
      const is503 = err?.response?.status === 503;
      setIsDbUnavailable(is503);
      setError(
        err?.response?.data?.detail ||
        (is503
          ? 'Database unavailable: SQL mode requires an active PostgreSQL connection.'
          : 'Failed to process your question. Please ensure the server is active.')
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

  // Helper to format table cells with R$ currency when appropriate
  const formatCellValue = (colName: string, val: any) => {
    if (val === null || val === undefined) return '—';
    if (typeof val === 'number') {
      const colLower = colName.toLowerCase();
      if (colLower.includes('price') || colLower.includes('revenue') || colLower.includes('amount') || colLower.includes('aov') || colLower.includes('val')) {
        return `R$ ${val.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
      }
      if (colLower.includes('pct') || colLower.includes('percent') || colLower.includes('rate')) {
        return `${val.toFixed(1)}%`;
      }
      return val.toLocaleString();
    }
    return String(val);
  };

  // Prepare chart data if numeric column exists
  const rows = response?.rows || [];
  const columns = response?.columns || (rows.length > 0 ? Object.keys(rows[0]) : []);
  const stringCol = columns.find(c => rows.some(r => typeof r[c] === 'string')) || columns[0];
  const numericCol = columns.find(c => rows.some(r => typeof r[c] === 'number' && !c.toLowerCase().includes('id')));

  const hasChartData = Boolean(numericCol && stringCol && rows.length > 0 && rows.length <= 50);
  const chartType = response?.suggested_chart || (stringCol?.toLowerCase().includes('month') || stringCol?.toLowerCase().includes('date') ? 'line' : 'bar');

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
              placeholder="Ask any natural-language business question (e.g. revenue, filters, categories, sellers)..."
              disabled={loading}
              className="w-full bg-slate-50 border border-slate-200 rounded-xl pl-4 pr-10 py-3.5 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-500 transition-all disabled:opacity-50"
            />
            {question && (
              <button
                onClick={() => setQuestion('')}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 text-xs font-bold cursor-pointer"
              >
                ✕
              </button>
            )}
          </div>

          <button
            onClick={() => handleAsk()}
            disabled={loading || !question.trim()}
            className="flex items-center space-x-2 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-xs px-5 py-3.5 rounded-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-xs active:scale-98 cursor-pointer"
          >
            {loading ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                <span>Querying...</span>
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
              className="text-xs bg-slate-100/80 hover:bg-indigo-50 text-slate-700 hover:text-indigo-600 border border-slate-200/80 hover:border-indigo-200 rounded-lg px-3 py-1.5 transition-all text-left disabled:opacity-50 font-medium cursor-pointer"
            >
              "{q}"
            </button>
          ))}
        </div>
      </div>

      {/* Error Message with 503 ErrorBanner */}
      {error && (
        <div className="mb-6">
          <ErrorBanner
            title={isDbUnavailable ? "Database Unavailable" : "Query Processing Error"}
            message={error}
            onRetry={() => handleAsk()}
          />
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

      {/* Result Card */}
      {response && !loading && (
        <div className="bg-slate-50/70 border border-slate-200/80 rounded-xl overflow-hidden shadow-xs transition-all space-y-4">
          {/* Metadata Header Bar */}
          <div className="bg-white border-b border-slate-200/80 px-5 py-3 flex flex-wrap items-center justify-between gap-2 text-xs">
            <div className="flex items-center space-x-2 text-slate-500 font-medium">
              <span>Query:</span>
              <span className="text-slate-900 font-semibold">"{response.question}"</span>
            </div>

            <div className="flex items-center space-x-2">
              <span className={`text-[11px] px-2.5 py-0.5 rounded-full font-medium border ${
                response.route === 'intent'
                  ? 'bg-blue-50 text-blue-700 border-blue-200'
                  : 'bg-indigo-50 text-indigo-700 border-indigo-200'
              }`}>
                {response.route === 'intent' ? 'Deterministic Intent Router' : 'Guarded Text-to-SQL'}
              </span>

              {response.grounding_verified && (
                <span className="text-[11px] bg-emerald-50 text-emerald-700 border border-emerald-200 px-2 py-0.5 rounded-full flex items-center space-x-1 font-medium">
                  <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                  <span>Grounding Verified</span>
                </span>
              )}
            </div>
          </div>

          {/* Explanation Body */}
          <div className="px-5 text-sm leading-relaxed text-slate-800 space-y-2">
            {response.explanation.split('\n').map((line, idx) => {
              if (!line.trim()) return <div key={idx} className="h-1" />;
              return (
                <p key={idx} className="mb-1.5 last:mb-0">
                  {renderFormattedText(line)}
                </p>
              );
            })}
          </div>

          {/* Assumptions List */}
          {response.assumptions && response.assumptions.length > 0 && (
            <div className="px-5 text-2xs text-slate-500">
              <span className="font-semibold text-slate-600">Assumptions applied:</span>{' '}
              {response.assumptions.join(' • ')}
            </div>
          )}

          {/* Action Tabs: Show SQL / Show Data Table */}
          <div className="px-5 flex items-center space-x-4 border-t border-slate-200/80 pt-3 text-xs">
            {response.sql && (
              <button
                onClick={() => setShowSql(!showSql)}
                className="flex items-center space-x-1 font-semibold text-indigo-600 hover:text-indigo-800 transition cursor-pointer"
              >
                <Code className="w-3.5 h-3.5" />
                <span>{showSql ? 'Hide SQL Query' : 'Show Generated SQL'}</span>
                {showSql ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
              </button>
            )}

            {rows.length > 0 && (
              <button
                onClick={() => setShowTable(!showTable)}
                className="flex items-center space-x-1 font-semibold text-slate-600 hover:text-slate-900 transition cursor-pointer"
              >
                <TableIcon className="w-3.5 h-3.5" />
                <span>{showTable ? 'Hide Table' : `Show Records (${response.row_count})`}</span>
              </button>
            )}
          </div>

          {/* "Show SQL" Collapsible Panel */}
          {showSql && response.sql && (
            <div className="mx-5 bg-slate-900 rounded-xl p-4 text-xs font-mono text-emerald-400 overflow-x-auto shadow-inner">
              <div className="text-slate-500 text-2xs mb-1">// Validated & Sanitized SQL (PostgreSQL readonly_engine)</div>
              <pre className="text-emerald-300 whitespace-pre-wrap">{response.sql}</pre>
            </div>
          )}

          {/* Suggested Chart Preview */}
          {hasChartData && (
            <div className="mx-5 bg-white border border-slate-200/80 rounded-xl p-4 shadow-2xs">
              <div className="flex items-center justify-between mb-3 text-xs">
                <span className="font-bold text-slate-800 flex items-center space-x-1.5">
                  {chartType === 'line' ? <TrendingUp className="w-3.5 h-3.5 text-indigo-600" /> : <BarChart2 className="w-3.5 h-3.5 text-indigo-600" />}
                  <span>Suggested Chart: {chartType === 'line' ? 'Time-Series Trend' : 'Categorical Comparison'}</span>
                </span>
                <span className="text-2xs text-slate-400 font-mono">
                  {stringCol} vs {numericCol}
                </span>
              </div>
              <div className="h-56 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  {chartType === 'line' ? (
                    <LineChart data={rows} margin={{ top: 10, right: 20, left: 20, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                      <XAxis dataKey={stringCol || 'label'} stroke="#94a3b8" fontSize={10} tickLine={false} />
                      <YAxis stroke="#94a3b8" fontSize={10} tickLine={false} />
                      <Tooltip />
                      <Line type="monotone" dataKey={numericCol || 'value'} stroke="#4f46e5" strokeWidth={2} dot={{ r: 3 }} />
                    </LineChart>
                  ) : (
                    <BarChart data={rows} margin={{ top: 10, right: 20, left: 20, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                      <XAxis dataKey={stringCol || 'label'} stroke="#94a3b8" fontSize={10} tickLine={false} />
                      <YAxis stroke="#94a3b8" fontSize={10} tickLine={false} />
                      <Tooltip />
                      <Bar dataKey={numericCol || 'value'} fill="#4f46e5" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  )}
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* Result Data Table */}
          {showTable && rows.length > 0 && (
            <div className="mx-5 mb-5 bg-white border border-slate-200/80 rounded-xl overflow-hidden shadow-2xs">
              <div className="px-4 py-2 bg-slate-50 border-b border-slate-200/80 flex items-center justify-between text-2xs text-slate-600">
                <span className="font-semibold uppercase tracking-wider">Query Records ({rows.length})</span>
                <span>Capped at max 500 rows</span>
              </div>
              <div className="overflow-x-auto max-h-64">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50/50 text-slate-500 font-semibold border-b border-slate-200/60 uppercase tracking-wider text-2xs sticky top-0">
                    <tr>
                      {columns.map((col, idx) => (
                        <th key={idx} className="py-2.5 px-4 font-mono">{col}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 text-slate-700 font-mono">
                    {rows.map((row, rIdx) => (
                      <tr key={rIdx} className="hover:bg-slate-50/60 transition">
                        {columns.map((col, cIdx) => (
                          <td key={cIdx} className="py-2 px-4 whitespace-nowrap">
                            {formatCellValue(col, row[col])}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
