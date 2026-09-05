import React from 'react';
import { Loader2 } from 'lucide-react';

interface LoadingSpinnerProps {
  message?: string;
}

export const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({ message = 'Loading analytics...' }) => {
  return (
    <div className="flex flex-col items-center justify-center p-8 text-slate-400 space-y-3 min-h-[160px]">
      <Loader2 className="w-7 h-7 animate-spin text-sky-400" />
      <span className="text-sm font-medium tracking-wide">{message}</span>
    </div>
  );
};
