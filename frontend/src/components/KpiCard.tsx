import React from 'react';
import { LucideIcon } from 'lucide-react';

interface KpiCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: LucideIcon;
  color?: 'blue' | 'emerald' | 'amber' | 'purple' | 'slate';
}

const colorStyles = {
  blue: 'text-sky-400 bg-sky-500/10 border-sky-500/20',
  emerald: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
  amber: 'text-amber-400 bg-amber-500/10 border-amber-500/20',
  purple: 'text-purple-400 bg-purple-500/10 border-purple-500/20',
  slate: 'text-slate-300 bg-slate-800/40 border-slate-700/40'
};

export const KpiCard: React.FC<KpiCardProps> = ({
  title,
  value,
  subtitle,
  icon: Icon,
  color = 'blue'
}) => {
  return (
    <div className="bg-slate-900/70 border border-slate-800/80 rounded-xl p-5 hover:border-slate-700/80 transition shadow-lg shadow-black/20">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">{title}</span>
        <div className={`p-2.5 rounded-lg border ${colorStyles[color]}`}>
          <Icon className="w-5 h-5" />
        </div>
      </div>
      <div className="mt-3">
        <span className="text-2xl sm:text-3xl font-bold tracking-tight text-white font-mono">{value}</span>
        {subtitle && <p className="text-xs text-slate-400 mt-1 font-medium">{subtitle}</p>}
      </div>
    </div>
  );
};
