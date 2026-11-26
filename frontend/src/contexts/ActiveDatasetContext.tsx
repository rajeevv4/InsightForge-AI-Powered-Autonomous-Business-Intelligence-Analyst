import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { api, getOwnerToken } from '../services/api';
import { DatasetSummary } from '../types/api';

/**
 * One active dataset for the whole app.
 * - Default: the built-in Olist demo (every page behaves exactly as before).
 * - Choice is persisted in localStorage (best effort; storage may be unavailable).
 * - If the stored dataset no longer exists or has expired, fall back to Olist with a notice.
 */

export const OLIST_DEMO_ID = '00000000-0000-0000-0000-000000000001';
const STORAGE_KEY = 'insightforge_active_dataset_id';

const readStored = (): string | null => {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
};

const writeStored = (id: string) => {
  try {
    window.localStorage.setItem(STORAGE_KEY, id);
  } catch {
    /* storage unavailable (private mode, blocked): keep in-memory only */
  }
};

export const isExpired = (ds: DatasetSummary | null | undefined, now: number = Date.now()): boolean =>
  !!ds?.expires_at && new Date(ds.expires_at).getTime() <= now;

interface ActiveDatasetContextValue {
  activeDatasetId: string;
  activeDataset: DatasetSummary | null;
  isOlist: boolean;
  /** True for Olist, or once the uploaded dataset is confirmed to exist in the live list. */
  activeReady: boolean;
  datasets: DatasetSummary[];
  datasetsLoaded: boolean;
  ownerToken: string;
  notice: string | null;
  dismissNotice: () => void;
  setActiveDatasetId: (id: string) => void;
  refreshDatasets: () => Promise<DatasetSummary[]>;
}

const ActiveDatasetContext = createContext<ActiveDatasetContextValue | null>(null);

export const ActiveDatasetProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [activeDatasetId, setActiveId] = useState<string>(() => readStored() || OLIST_DEMO_ID);
  const [datasets, setDatasets] = useState<DatasetSummary[]>([]);
  const [datasetsLoaded, setDatasetsLoaded] = useState<boolean>(false);
  const [notice, setNotice] = useState<string | null>(null);
  const activeIdRef = useRef<string>(activeDatasetId);
  const ownerToken = useMemo(() => getOwnerToken(), []);

  const setActiveDatasetId = useCallback((id: string) => {
    activeIdRef.current = id;
    setActiveId(id);
    writeStored(id);
  }, []);

  const fallBackToOlist = useCallback((message: string) => {
    setActiveDatasetId(OLIST_DEMO_ID);
    setNotice(message);
  }, [setActiveDatasetId]);

  /** Reload the dataset list and re-validate the active selection against it. */
  const refreshDatasets = useCallback(async (): Promise<DatasetSummary[]> => {
    let list: DatasetSummary[];
    try {
      list = await api.getDatasets();
    } catch (e) {
      // Cannot verify right now (server down): keep the current choice; pages show their own errors.
      console.warn('Could not load datasets list:', e);
      setDatasetsLoaded(true);
      return datasets;
    }
    setDatasets(list);
    setDatasetsLoaded(true);
    const current = activeIdRef.current;
    if (current !== OLIST_DEMO_ID) {
      const found = list.find((d) => d.id === current);
      if (!found) {
        fallBackToOlist('The previously selected dataset no longer exists. Switched to the Olist demo.');
      } else if (isExpired(found)) {
        fallBackToOlist(`Dataset "${found.name}" has expired. Switched to the Olist demo.`);
      }
    }
    return list;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fallBackToOlist]);

  useEffect(() => {
    refreshDatasets();
  }, [refreshDatasets]);

  // Expire the active upload while the app is open.
  useEffect(() => {
    const timer = window.setInterval(() => {
      const ds = datasets.find((d) => d.id === activeIdRef.current);
      if (ds && !ds.is_demo && isExpired(ds)) {
        fallBackToOlist(`Dataset "${ds.name}" has expired. Switched to the Olist demo.`);
      }
    }, 60000);
    return () => window.clearInterval(timer);
  }, [datasets, fallBackToOlist]);

  const value = useMemo<ActiveDatasetContextValue>(() => {
    const activeDataset = datasets.find((d) => d.id === activeDatasetId) || null;
    return {
      activeDatasetId,
      activeDataset,
      isOlist: activeDatasetId === OLIST_DEMO_ID,
      activeReady: activeDatasetId === OLIST_DEMO_ID || (!!activeDataset && !isExpired(activeDataset)),
      datasets,
      datasetsLoaded,
      ownerToken,
      notice,
      dismissNotice: () => setNotice(null),
      setActiveDatasetId: (id: string) => {
        setNotice(null);
        setActiveDatasetId(id);
      },
      refreshDatasets,
    };
  }, [activeDatasetId, datasets, datasetsLoaded, ownerToken, notice, setActiveDatasetId, refreshDatasets]);

  return <ActiveDatasetContext.Provider value={value}>{children}</ActiveDatasetContext.Provider>;
};

export const useActiveDataset = (): ActiveDatasetContextValue => {
  const ctx = useContext(ActiveDatasetContext);
  if (!ctx) throw new Error('useActiveDataset must be used inside <ActiveDatasetProvider>');
  return ctx;
};

/** Route-level switch: renders the Olist page unchanged, or the custom-dataset page. */
export const DatasetAware: React.FC<{ olist: React.ReactElement; custom: React.ReactElement }> = ({ olist, custom }) => {
  const { isOlist, activeReady, datasetsLoaded } = useActiveDataset();
  if (isOlist) return olist;
  if (!activeReady) {
    // Never flash Olist data while an uploaded dataset is being validated.
    return (
      <div className="bg-white border border-slate-200/80 rounded-2xl p-8 shadow-xs text-xs text-slate-500">
        {datasetsLoaded ? 'The selected dataset is not available right now (server unreachable?).' : 'Loading dataset…'}
      </div>
    );
  }
  return custom;
};
