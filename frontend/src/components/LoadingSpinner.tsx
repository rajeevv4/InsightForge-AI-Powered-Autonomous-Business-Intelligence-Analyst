import React from 'react';
import { Loader2 } from 'lucide-react';

interface LoadingSpinnerProps {
  message?: string;
}

export const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({ message = 'Loading analytics...' }) => {
  return (
    <div className="flex flex-col items-center justify-center p-8 text-slate-500 space-y-3 min-h-[160px] bg-white border border-slate-200/80 rounded-xl">
      <Loader2 className="w-6 h-6 animate-spin text-indigo-600" />
      <span className="text-xs font-medium">{message}</span>
    </div>
  );
};
