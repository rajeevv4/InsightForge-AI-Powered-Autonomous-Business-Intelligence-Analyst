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
    <div className="flex flex-col sm:flex-row items-center justify-between p-4 bg-rose-50 border border-rose-200/80 rounded-xl text-rose-900 text-xs space-y-2 sm:space-y-0">
      <div className="flex items-center space-x-3">
        <AlertCircle className="w-5 h-5 text-rose-600 shrink-0" />
        <div>
          <p className="font-bold text-rose-900">{title}</p>
          <p className="text-rose-700 text-xs mt-0.5">{message}</p>
        </div>
      </div>
      {onRetry && (
        <button
          onClick={onRetry}
          className="px-3.5 py-1.5 bg-white hover:bg-rose-100 border border-rose-200 text-rose-800 rounded-lg text-xs transition font-semibold shadow-2xs"
        >
          Try Again
        </button>
      )}
    </div>
  );
};
