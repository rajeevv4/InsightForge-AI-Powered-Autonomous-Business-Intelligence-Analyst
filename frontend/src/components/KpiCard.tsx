import React from 'react';
import { LucideIcon } from 'lucide-react';
import { CountUp } from './ui';

interface KpiCardProps {
  title: string;
  /** Pre-formatted display value (used as-is when numericValue is not given). */
  value: string | number;
  /** Optional raw number: the card counts up to it and then shows format(numericValue) (same text as `value`). */
  numericValue?: number | null;
  format?: (v: number) => string;
  subtitle?: string;
  icon: LucideIcon;
  color?: 'blue' | 'emerald' | 'amber' | 'purple' | 'indigo' | 'slate';
}

const colorStyles = {
  blue: 'text-blue-600 bg-blue-50 border-blue-100',
  emerald: 'text-emerald-600 bg-emerald-50 border-emerald-100',
  amber: 'text-amber-600 bg-amber-50 border-amber-100',
  purple: 'text-purple-600 bg-purple-50 border-purple-100',
  indigo: 'text-indigo-600 bg-indigo-50 border-indigo-100',
  slate: 'text-slate-600 bg-slate-100 border-slate-200'
};

const accent = {
  blue: 'from-blue-500 to-cyan-400',
  emerald: 'from-emerald-500 to-teal-400',
  amber: 'from-amber-500 to-orange-400',
  purple: 'from-purple-500 to-fuchsia-400',
  indigo: 'from-indigo-500 to-violet-500',
  slate: 'from-slate-400 to-slate-300',
};

export const KpiCard: React.FC<KpiCardProps> = ({
  title,
  value,
  numericValue,
  format,
  subtitle,
  icon: Icon,
  color = 'indigo'
}) => {
  const display = numericValue !== undefined && numericValue !== null && format
    ? <CountUp value={numericValue} format={format} />
    : value;
  return (
    <div className="group relative overflow-hidden bg-white border border-slate-200/80 rounded-2xl p-5 shadow-xs flex flex-col justify-between min-w-0 card-lift">
      <span aria-hidden="true" className={`absolute inset-x-0 top-0 h-1 bg-gradient-to-r ${accent[color]} opacity-70 group-hover:opacity-100 transition-opacity`} />
      <div className="flex items-center justify-between gap-2 min-w-0">
        <span className="text-xs font-bold uppercase tracking-wider text-slate-500 truncate" title={title}>{title}</span>
        <div className={`p-2 rounded-xl border shrink-0 transition-transform group-hover:scale-110 ${colorStyles[color]}`}>
          <Icon className="w-4 h-4" />
        </div>
      </div>
      <div className="mt-4 min-w-0">
        <div className="text-xl sm:text-[1.35rem] 2xl:text-2xl font-extrabold tracking-tight text-slate-900 truncate tabular-nums" title={typeof value === 'string' ? value : String(value)}>
          {display}
        </div>
        {subtitle && (
          <p className="text-xs text-slate-500 mt-1 font-medium truncate" title={subtitle}>
            {subtitle}
          </p>
        )}
      </div>
    </div>
  );
};
