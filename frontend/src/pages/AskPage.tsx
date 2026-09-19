import React from 'react';
import { AskInsightForge } from '../components/AskInsightForge';
import { Sparkles, ArrowRight, ShieldCheck, Database, Cpu, FileText } from 'lucide-react';

export const AskPage: React.FC = () => {
  return (
    <div className="space-y-8 pb-12">
      {/* Page Heading */}
      <div className="border-b border-slate-800/80 pb-4">
        <h1 className="text-2xl font-extrabold text-white tracking-tight flex items-center gap-2">
          Ask InsightForge AI
          <span className="text-xs bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 px-3 py-1 rounded-full font-mono font-medium">
            Gemini 2.5 Flash
          </span>
        </h1>
        <p className="text-xs text-slate-400 mt-1">
          Ask business questions in natural language. Powered by AI intent classification grounded strictly in validated PostgreSQL data.
        </p>
      </div>

      {/* Main AI Component */}
      <section>
        <AskInsightForge />
      </section>

      {/* "How InsightForge Answers" Explanatory Architecture Diagram */}
      <section className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-6 backdrop-blur-sm">
        <div className="flex items-center space-x-2 mb-4">
          <Sparkles className="w-4 h-4 text-cyan-400" />
          <h3 className="text-sm font-bold text-white tracking-tight">How InsightForge Answers Business Questions</h3>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-5 gap-3 text-xs">
          {/* Step 1 */}
          <div className="bg-slate-950/80 border border-slate-800 p-3.5 rounded-xl flex flex-col items-center text-center">
            <div className="w-8 h-8 rounded-lg bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 flex items-center justify-center font-bold mb-2">
              1
            </div>
            <span className="font-semibold text-slate-200">Natural-Language Question</span>
            <span className="text-[10px] text-slate-400 mt-1">Free-form business query</span>
          </div>

          {/* Step 2 */}
          <div className="bg-slate-950/80 border border-slate-800 p-3.5 rounded-xl flex flex-col items-center text-center">
            <div className="w-8 h-8 rounded-lg bg-blue-500/10 text-blue-400 border border-blue-500/30 flex items-center justify-center font-bold mb-2">
              2
            </div>
            <span className="font-semibold text-slate-200">AI Intent Classification</span>
            <span className="text-[10px] text-slate-400 mt-1">Maps to 8 allow-listed intents</span>
          </div>

          {/* Step 3 */}
          <div className="bg-slate-950/80 border border-slate-800 p-3.5 rounded-xl flex flex-col items-center text-center">
            <div className="w-8 h-8 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/30 flex items-center justify-center font-bold mb-2">
              3
            </div>
            <span className="font-semibold text-slate-200">Validated Router</span>
            <span className="text-[10px] text-slate-400 mt-1">Executes trusted Python analytics</span>
          </div>

          {/* Step 4 */}
          <div className="bg-slate-950/80 border border-slate-800 p-3.5 rounded-xl flex flex-col items-center text-center">
            <div className="w-8 h-8 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 flex items-center justify-center font-bold mb-2">
              4
            </div>
            <span className="font-semibold text-slate-200">PostgreSQL Evidence</span>
            <span className="text-[10px] text-slate-400 mt-1">Real database view metrics</span>
          </div>

          {/* Step 5 */}
          <div className="bg-slate-950/80 border border-slate-800 p-3.5 rounded-xl flex flex-col items-center text-center">
            <div className="w-8 h-8 rounded-lg bg-purple-500/10 text-purple-400 border border-purple-500/30 flex items-center justify-center font-bold mb-2">
              5
            </div>
            <span className="font-semibold text-slate-200">Grounded Explanation</span>
            <span className="text-[10px] text-slate-400 mt-1">Zero-hallucination synthesis</span>
          </div>
        </div>
      </section>
    </div>
  );
};
