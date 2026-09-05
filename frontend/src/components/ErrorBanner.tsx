import React from 'react';
import { AlertCircle } from 'lucide-react';

interface ErrorBannerProps {
  title?: string;
  message?: string;
  onRetry?: () => void;
}

export const ErrorBanner: React.FC<ErrorBannerProps> = ({
  title = 'Unable to load section',
  message = 'An error occurred while connecting to the API server.',
  onRetry,
}) => {
  return (
    <div className="flex flex-col sm:flex-row items-center justify-between p-4 bg-rose-950/40 border border-rose-800/50 rounded-xl text-rose-200 text-sm space-y-2 sm:space-y-0">
      <div className="flex items-center space-x-3">
        <AlertCircle className="w-5 h-5 text-rose-400 shrink-0" />
        <div>
          <p className="font-semibold text-rose-300">{title}</p>
          <p className="text-rose-400/80 text-xs mt-0.5">{message}</p>
        </div>
      </div>
      {onRetry && (
        <button
          onClick={onRetry}
          className="px-3 py-1.5 bg-rose-900/60 hover:bg-rose-800/60 border border-rose-700/60 text-rose-100 rounded-lg text-xs transition font-medium"
        >
          Try Again
        </button>
      )}
    </div>
  );
};
