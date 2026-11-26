import { formatMoney } from '../lib/format';
import { useUi } from '../contexts/UiContext';
import React, { useState, useRef, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import {
  Sparkles,
  HelpCircle,
  CheckCircle2,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  Table as TableIcon,
  BarChart2,
  TrendingUp,
  PieChart as PieChartIcon,
  Code,
  Mic,
  Square,
  Volume2,
  VolumeX,
  Languages,
  ShieldCheck,
  ShieldAlert,
  AlertCircle,
  Database,
  Layers,
  Check,
  Edit3,
  LayoutDashboard
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
import { AnomalyExplainDrawer, ExplainButton, ExplainTarget } from './AnomalyExplainDrawer';
import { api } from '../services/api';
import {
  DatasetAskResponse,
  DatasetInsightsResponse,
  DatasetSemanticResponse,
  DatasetSummary,
  SQLAskResponse,
  UpdateDatasetSemanticRequest
} from '../types/api';
import { ErrorBanner } from './ErrorBanner';
import { DatasetDashboard } from './DatasetDashboard';
import { useActiveDataset } from '../contexts/ActiveDatasetContext';

const OLIST_DEMO_ID = '00000000-0000-0000-0000-000000000001';

const EXAMPLE_QUESTIONS = {
  en: [
    "Which category generated the highest revenue?",
    "What is our average order value?",
    "Which customer states generated the most sales in 2017?",
    "How is our on-time delivery performance?",
    "Top 5 sellers by fulfilled orders?",
    "Show monthly gross revenue trend for 2018."
  ],
  hi: [
    "सबसे ज्यादा बिक्री किस श्रेणी में हुई?",
    "कुल सकल राजस्व (gross revenue) कितना है?",
    "समय पर डिलीवरी का प्रतिशत कितना है?",
    "ब्राजील के किस राज्य से सबसे अधिक बिक्री हुई?",
    "सर्वश्रेष्ठ प्रदर्शन करने वाला विक्रेता कौन है?",
    "क्रेडिट कार्ड से कुल कितना भुगतान हुआ?"
  ],
  hinglish: [
    "sabse zyada bikri kis product category mein hui?",
    "overall gross revenue aur delivered orders kitne hain?",
    "hamara on-time delivery rate kitna hai?",
    "kaunse state se sabse jyada customer orders aaye?",
    "kya koi black friday sales spike ya anomaly detect hui?"
  ]
};

export const AskInsightForge: React.FC = () => {
  // Shared app-wide selection AND dataset list (header switcher, Overview widget and this dropdown stay in sync)
  const {
    activeDatasetId: selectedDatasetId,
    setActiveDatasetId: setSelectedDatasetId,
    datasets,
    refreshDatasets,
    activeReady,
  } = useActiveDataset();
  const [selectedDataset, setSelectedDataset] = useState<DatasetSummary | null>(null);

  // Tabs: 'ask' | 'insights' | 'semantic'
  const [activeTab, setActiveTab] = useState<'ask' | 'insights' | 'semantic' | 'dashboard'>('ask');

  // Query State
  const [question, setQuestion] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [isDbUnavailable, setIsDbUnavailable] = useState<boolean>(false);

  // Olist Ask Response vs Custom Dataset Ask Response
  const [olistResponse, setOlistResponse] = useState<SQLAskResponse | null>(null);
  const [datasetResponse, setDatasetResponse] = useState<DatasetAskResponse | null>(null);

  // Quick Insights State
  const [insights, setInsights] = useState<DatasetInsightsResponse | null>(null);
  const [insightsLoading, setInsightsLoading] = useState<boolean>(false);
  const [insightsError, setInsightsError] = useState<string | null>(null);
  const [explainTarget, setExplainTarget] = useState<ExplainTarget | null>(null);
  const { currency: pickedCurrency } = useUi();

  // Semantic Layer State
  const [semantic, setSemantic] = useState<DatasetSemanticResponse | null>(null);
  const [semanticLoading, setSemanticLoading] = useState<boolean>(false);
  const [semanticConfirming, setSemanticConfirming] = useState<boolean>(false);
  const [semanticSuccessMsg, setSemanticSuccessMsg] = useState<string | null>(null);

  // Display toggles
  const [showSql, setShowSql] = useState<boolean>(false);
  const [showTable, setShowTable] = useState<boolean>(true);

  // Voice & Multilingual State
  const [selectedLanguage, setSelectedLanguage] = useState<'auto' | 'hi' | 'en'>('auto');
  const [isRecording, setIsRecording] = useState<boolean>(false);
  const [recordingSeconds, setRecordingSeconds] = useState<number>(0);
  const [isTranscribing, setIsTranscribing] = useState<boolean>(false);
  const [voiceNotice, setVoiceNotice] = useState<string | null>(null);
  const [isSpeaking, setIsSpeaking] = useState<boolean>(false);
  const [speechWarning, setSpeechWarning] = useState<string | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const timerIntervalRef = useRef<number | null>(null);

  const isCustomDataset = selectedDatasetId !== OLIST_DEMO_ID;
  // Latest selected dataset, read by async loaders to discard stale responses.
  const selectedDatasetIdRef = useRef<string>(selectedDatasetId);

  // Load datasets list on mount
  useEffect(() => {
    loadDatasetsList();
    return () => {
      if (timerIntervalRef.current) {
        window.clearInterval(timerIntervalRef.current);
      }
      if (window.speechSynthesis) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  // When selected dataset changes, fetch semantic model and reset state.
  // Keyed on the id only: the shared list refreshes (e.g. when the header switcher opens)
  // and that must not wipe the current answer or reload the semantic layer.
  useEffect(() => {
    setError(null);
    setOlistResponse(null);
    setDatasetResponse(null);
    setVoiceNotice(null);
    // Drop the previous dataset's semantic model so its starter questions never show for this one.
    setSemantic(null);
    selectedDatasetIdRef.current = selectedDatasetId;
    setExplainTarget(null);

    // Only once the uploaded dataset is confirmed to exist (no requests for stale stored ids).
    if (selectedDatasetId !== OLIST_DEMO_ID && activeReady) {
      loadSemanticLayer(selectedDatasetId);
      loadQuickInsights(selectedDatasetId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedDatasetId, activeReady]);

  // Keep the selected dataset's summary (name, share_samples) in step with the shared list.
  useEffect(() => {
    setSelectedDataset(datasets.find((d) => d.id === selectedDatasetId) || null);
  }, [selectedDatasetId, datasets]);

  const loadDatasetsList = async () => {
    await refreshDatasets();
  };

  const loadSemanticLayer = async (dsId: string) => {
    setSemanticLoading(true);
    try {
      const sem = await api.getDatasetSemantic(dsId);
      // The first fetch can take several seconds (draft + enrichment); ignore it if the
      // user has switched to another dataset in the meantime.
      if (selectedDatasetIdRef.current !== dsId) return;
      setSemantic(sem);
    } catch (e: any) {
      console.warn('Could not fetch semantic layer:', e);
    } finally {
      setSemanticLoading(false);
    }
  };

  const loadQuickInsights = async (dsId: string) => {
    setInsightsLoading(true);
    setInsightsError(null);
    try {
      const data = await api.getDatasetInsights(dsId);
      setInsights(data);
    } catch (e: any) {
      console.warn('Could not fetch dataset insights:', e);
      setInsightsError('Insights unavailable. Server may be in fixture mode or dataset has no tables.');
    } finally {
      setInsightsLoading(false);
    }
  };

  const handleAsk = async (queryToAsk?: string) => {
    const targetQuestion = (queryToAsk !== undefined ? queryToAsk : question).trim();
    if (!targetQuestion) return;

    setQuestion(targetQuestion);
    setLoading(true);
    setError(null);
    setIsDbUnavailable(false);
    setShowSql(false);
    setVoiceNotice(null);

    if (window.speechSynthesis) {
      window.speechSynthesis.cancel();
      setIsSpeaking(false);
    }

    try {
      if (isCustomDataset) {
        const result = await api.askDataset(selectedDatasetId, targetQuestion, selectedLanguage);
        setDatasetResponse(result);
      } else {
        const result = await api.sqlAskAI(targetQuestion);
        setOlistResponse(result);
      }
    } catch (err: any) {
      console.error('Failed to query AI:', err);
      const is503 = err?.response?.status === 503;
      const is429 = err?.response?.status === 429;
      setIsDbUnavailable(is503);
      if (is429) {
        setError('AI quota reached. Please try again later or consult the pre-computed dataset insights.');
      } else {
        setError(
          err?.response?.data?.detail ||
          (is503
            ? 'Database unavailable: SQL mode requires an active PostgreSQL connection.'
            : 'Failed to process your question. Please ensure the server is active.')
        );
      }
    } finally {
      setLoading(false);
    }
  };

  // Questions submitted from the header search arrive via navigation state.
  // Keyed on location.key so each search runs once (StrictMode re-runs effects in dev).
  const location = useLocation();
  const handledNavKeyRef = useRef<string | null>(null);
  useEffect(() => {
    const incoming = (location.state as { question?: string } | null)?.question;
    if (incoming && handledNavKeyRef.current !== location.key) {
      handledNavKeyRef.current = location.key;
      handleAsk(incoming);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.key]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !loading) {
      handleAsk();
    }
  };

  const handleConfirmSemantic = async () => {
    if (!semantic) return;
    setSemanticConfirming(true);
    try {
      const updated = await api.updateDatasetSemantic(selectedDatasetId, {
        status: 'confirmed'
      });
      setSemantic(updated);
      setSemanticSuccessMsg('Semantic model successfully confirmed!');
      setTimeout(() => setSemanticSuccessMsg(null), 4000);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to confirm semantic model');
    } finally {
      setSemanticConfirming(false);
    }
  };

  // Voice Recording handlers
  const startRecording = async () => {
    setVoiceNotice(null);
    setError(null);

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setVoiceNotice('Microphone audio recording is not supported in this browser. Please type your question.');
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunksRef.current = [];

      let mimeType = 'audio/webm';
      if (typeof MediaRecorder !== 'undefined') {
        if (MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) {
          mimeType = 'audio/webm;codecs=opus';
        } else if (MediaRecorder.isTypeSupported('audio/webm')) {
          mimeType = 'audio/webm';
        } else if (MediaRecorder.isTypeSupported('audio/ogg')) {
          mimeType = 'audio/ogg';
        } else if (MediaRecorder.isTypeSupported('audio/mp4')) {
          mimeType = 'audio/mp4';
        } else {
          mimeType = '';
        }
      }

      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      recorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        if (timerIntervalRef.current) {
          window.clearInterval(timerIntervalRef.current);
          timerIntervalRef.current = null;
        }
        setIsRecording(false);

        const chosenMime = recorder.mimeType || mimeType || 'audio/webm';
        const audioBlob = new Blob(audioChunksRef.current, { type: chosenMime });

        if (audioBlob.size < 100) {
          setVoiceNotice('Recording was too short. Please speak for at least 1-2 seconds and try again.');
          return;
        }
        await processAudioTranscription(audioBlob);
      };

      recorder.start(250);
      setIsRecording(true);
      setRecordingSeconds(0);
      setVoiceNotice(
        `Listening in ${selectedLanguage === 'hi' ? 'Hindi (हिन्दी)' : 'English / Hinglish'}... Speak clearly into your microphone.`
      );

      timerIntervalRef.current = window.setInterval(() => {
        setRecordingSeconds((prev) => {
          if (prev >= 59) {
            stopRecording();
            return 60;
          }
          return prev + 1;
        });
      }, 1000);
    } catch (err: any) {
      if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
        setVoiceNotice('Microphone access was denied. Please allow microphone permissions in your browser.');
      } else {
        setVoiceNotice('Could not start microphone recording. Please type your question directly.');
      }
      setIsRecording(false);
    }
  };

  const stopRecording = () => {
    if (timerIntervalRef.current) {
      window.clearInterval(timerIntervalRef.current);
      timerIntervalRef.current = null;
    }

    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      try {
        if (mediaRecorderRef.current.state === 'recording') {
          mediaRecorderRef.current.requestData();
        }
        mediaRecorderRef.current.stop();
      } catch (e) {
        console.error('Error stopping MediaRecorder:', e);
      }
    }
    setIsRecording(false);
  };

  const processAudioTranscription = async (blob: Blob) => {
    setIsTranscribing(true);
    setVoiceNotice('Transcribing audio with Gemini AI...');
    try {
      const ext = blob.type.includes('ogg') ? 'ogg' : blob.type.includes('mp4') ? 'm4a' : 'webm';
      const result = await api.transcribeVoice(blob, `voice_query.${ext}`);
      if (result.text && result.text.trim()) {
        setQuestion(result.text.trim());
        const langLabel =
          result.detected_language === 'hi'
            ? 'Hindi (हिन्दी)'
            : result.detected_language === 'hinglish'
            ? 'Hinglish (हिंग्लिश)'
            : 'English';
        setVoiceNotice(
          `Transcribed in ${langLabel} (${(result.confidence * 100).toFixed(0)}% confidence). Review and click Ask AI.`
        );
      } else {
        setVoiceNotice('No clear speech was recognized. Please try speaking again or type your question.');
      }
    } catch (err: any) {
      const status = err?.response?.status;
      const detail = err?.response?.data?.detail;
      if (status === 429) {
        setVoiceNotice('Gemini API quota reached. Please type your question directly.');
      } else if (status === 503) {
        setVoiceNotice(detail || 'AI voice service is temporarily unavailable. Please type your question.');
      } else {
        setVoiceNotice(detail || 'Voice transcription encountered an issue. Please type your question directly.');
      }
    } finally {
      setIsTranscribing(false);
    }
  };

  // Plain-text cell formatting
  const formatCellValue = (colName: string, val: any): string => {
    if (val === null || val === undefined) return '—';
    if (typeof val === 'number') {
      const lower = colName.toLowerCase();
      if (lower.includes('price') || lower.includes('revenue') || lower.includes('freight') || lower.includes('amount') || lower.includes('value')) {
        // Olist: R$; uploads: the currency picked for this dataset (or plain numbers when none)
        return formatMoney(val, !isCustomDataset ? 'R$' : pickedCurrency);
      }
      return Number.isInteger(val) ? val.toLocaleString() : val.toFixed(2);
    }
    return String(val);
  };

  // Determine current active response
  const activeResponse = isCustomDataset ? datasetResponse : olistResponse;
  const rows = isCustomDataset ? (datasetResponse?.data_rows || []) : (olistResponse?.rows || []);
  const columns = isCustomDataset ? (datasetResponse?.columns || []) : (olistResponse?.columns || []);
  const privacyBadge = isCustomDataset
    ? (datasetResponse?.privacy_badge || (selectedDataset?.share_samples ? 'AI sees: schema + data' : 'AI sees: schema only'))
    : null;

  // Chart configuration for response
  const stringCol = columns.find((c) => {
    const val = rows[0]?.[c];
    return typeof val === 'string';
  });
  const numericCol = columns.find((c) => {
    const val = rows[0]?.[c];
    return typeof val === 'number';
  });
  const hasChartData = Boolean(rows.length > 0 && stringCol && numericCol && rows.length <= 50);

  return (
    <div className="space-y-6">
      {/* Top Controls: Dataset Selector + Privacy Badge */}
      <div className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-xs">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center space-x-3">
            <div className="p-2.5 bg-indigo-50 text-indigo-600 rounded-xl">
              <Database className="w-5 h-5" />
            </div>
            <div>
              <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                Asking Dataset
              </div>
              <div className="text-sm font-bold text-slate-900 mt-0.5">
                Asking: <span className="text-indigo-600">{selectedDataset?.name || 'Olist E-Commerce'}</span>
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {/* Dataset Selector Dropdown */}
            <div className="relative">
              <select
                value={selectedDatasetId}
                onChange={(e) => setSelectedDatasetId(e.target.value)}
                className="appearance-none bg-slate-50 border border-slate-200 text-slate-800 text-xs font-semibold rounded-xl pl-3 pr-8 py-2 hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 cursor-pointer"
              >
                <option value={OLIST_DEMO_ID}>Olist E-Commerce (Demo dataset)</option>
                {datasets
                  .filter((d) => !d.is_demo)
                  .map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name} ({d.schema_name})
                    </option>
                  ))}
              </select>
              <ChevronDown className="w-4 h-4 text-slate-400 absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
            </div>

            {/* Privacy Badge for Custom Datasets */}
            {isCustomDataset && (
              <span
                className={`inline-flex items-center space-x-1.5 px-3 py-1 rounded-full text-xs font-semibold border ${
                  selectedDataset?.share_samples
                    ? 'bg-amber-50 text-amber-700 border-amber-200'
                    : 'bg-emerald-50 text-emerald-700 border-emerald-200'
                }`}
                title={
                  selectedDataset?.share_samples
                    ? 'Sample data values may be sent to AI for narrative explanations'
                    : 'Strict Privacy: AI receives table/column schema only; zero data rows or cell values are ever transmitted to any LLM'
                }
              >
                {selectedDataset?.share_samples ? (
                  <ShieldAlert className="w-3.5 h-3.5" />
                ) : (
                  <ShieldCheck className="w-3.5 h-3.5" />
                )}
                <span>
                  {selectedDataset?.share_samples ? 'AI sees: schema + data' : 'AI sees: schema only'}
                </span>
              </span>
            )}
          </div>
        </div>

        {/* Tab Switcher for Uploaded Datasets */}
        {isCustomDataset && (
          <div role="tablist" aria-label="Dataset tools" className="flex border-b border-slate-100 mt-5 pt-3 gap-6 text-xs font-semibold overflow-x-auto whitespace-nowrap -mx-1 px-1">
            <button
              onClick={() => setActiveTab('ask')}
              className={`pb-2.5 flex items-center space-x-2 border-b-2 transition-colors cursor-pointer ${
                activeTab === 'ask'
                  ? 'border-indigo-600 text-indigo-600'
                  : 'border-transparent text-slate-500 hover:text-slate-800'
              }`}
            >
              <Sparkles className="w-4 h-4" />
              <span>Ask AI</span>
            </button>

            <button
              onClick={() => setActiveTab('insights')}
              className={`pb-2.5 flex items-center space-x-2 border-b-2 transition-colors cursor-pointer ${
                activeTab === 'insights'
                  ? 'border-indigo-600 text-indigo-600'
                  : 'border-transparent text-slate-500 hover:text-slate-800'
              }`}
            >
              <BarChart2 className="w-4 h-4" />
              <span>Quick Insights & Anomalies</span>
            </button>

            <button
              onClick={() => setActiveTab('semantic')}
              className={`pb-2.5 flex items-center space-x-2 border-b-2 transition-colors cursor-pointer ${
                activeTab === 'semantic'
                  ? 'border-indigo-600 text-indigo-600'
                  : 'border-transparent text-slate-500 hover:text-slate-800'
              }`}
            >
              <Layers className="w-4 h-4" />
              <span>Semantic Layer ({semantic?.status || 'draft'})</span>
            </button>

            <button
              onClick={() => setActiveTab('dashboard')}
              className={`pb-2.5 flex items-center space-x-2 border-b-2 transition-colors cursor-pointer ${
                activeTab === 'dashboard'
                  ? 'border-indigo-600 text-indigo-600'
                  : 'border-transparent text-slate-500 hover:text-slate-800'
              }`}
            >
              <LayoutDashboard className="w-4 h-4" />
              <span>Dashboard</span>
            </button>
          </div>
        )}
      </div>

      {/* TAB 1: ASK AI */}
      {(!isCustomDataset || activeTab === 'ask') && (
        <div className="bg-white border border-slate-200/80 rounded-2xl p-6 shadow-xs space-y-5">
          {/* Starter Questions / Clickable Chips */}
          <div>
            <div className="flex items-center space-x-2 mb-2.5 text-slate-700 font-bold text-xs">
              <Sparkles className="w-3.5 h-3.5 text-indigo-600" />
              <span>
                {isCustomDataset
                  ? 'Starter Questions from Semantic Model:'
                  : 'Suggested Questions (English & Hindi):'}
              </span>
            </div>
            {/* Olist example chips are only for the built-in demo; custom datasets show their own or a hint. */}
            {isCustomDataset && !(semantic?.starter_questions && semantic.starter_questions.length > 0) && (
              <p className="text-xs text-slate-500">
                {semanticLoading ? 'Preparing starter questions for this dataset…' : 'Type a question about your data.'}
              </p>
            )}
            <div className="flex flex-wrap gap-2">
              {(isCustomDataset ? semantic?.starter_questions ?? [] : EXAMPLE_QUESTIONS.en).map((q, idx) => (
                <button
                  key={idx}
                  onClick={() => handleAsk(q)}
                  disabled={loading}
                  className="px-3 py-1.5 bg-slate-50 hover:bg-indigo-50 hover:text-indigo-700 hover:border-indigo-200 border border-slate-200/80 rounded-xl text-xs text-slate-700 transition cursor-pointer text-left"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>

          {/* Language Selector & Recording Indicator */}
          <div className="flex flex-wrap items-center justify-between text-2xs text-slate-500 gap-2 px-1">
            <div className="flex items-center space-x-2">
              <span className="flex items-center space-x-1 font-medium text-slate-600">
                <Languages className="w-3.5 h-3.5 text-indigo-500" />
                <span>Speech Language:</span>
              </span>
              <div className="inline-flex rounded-lg border border-slate-200 bg-slate-50 p-0.5">
                <button
                  type="button"
                  onClick={() => setSelectedLanguage('auto')}
                  className={`px-2 py-0.5 rounded-md font-medium transition cursor-pointer ${
                    selectedLanguage === 'auto'
                      ? 'bg-white text-indigo-600 shadow-2xs font-semibold'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  Auto
                </button>
                <button
                  type="button"
                  onClick={() => setSelectedLanguage('en')}
                  className={`px-2 py-0.5 rounded-md font-medium transition cursor-pointer ${
                    selectedLanguage === 'en'
                      ? 'bg-white text-indigo-600 shadow-2xs font-semibold'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  English (en-IN)
                </button>
                <button
                  type="button"
                  onClick={() => setSelectedLanguage('hi')}
                  className={`px-2 py-0.5 rounded-md font-medium transition cursor-pointer ${
                    selectedLanguage === 'hi'
                      ? 'bg-white text-indigo-600 shadow-2xs font-semibold'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  हिन्दी (hi-IN)
                </button>
              </div>
            </div>

            {isRecording && (
              <div className="flex items-center space-x-1.5 text-rose-600 font-semibold bg-rose-50 border border-rose-100 px-2 py-0.5 rounded-md">
                <span className="w-2 h-2 rounded-full bg-rose-500 animate-ping"></span>
                <span>
                  Recording: {Math.floor(recordingSeconds / 60)}:{(recordingSeconds % 60).toString().padStart(2, '0')} / 1:00
                </span>
              </div>
            )}
            {isTranscribing && (
              <div className="flex items-center space-x-1.5 text-indigo-600 font-semibold bg-indigo-50 border border-indigo-100 px-2 py-0.5 rounded-md">
                <RefreshCw className="w-3 h-3 animate-spin text-indigo-600" />
                <span>Transcribing speech...</span>
              </div>
            )}
          </div>

          {/* Question Input Box + Voice Recording */}
          <div className="space-y-2">
            <div className="relative flex items-center">
              <input
                type="text"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={
                  isRecording
                    ? 'Listening... Speak your question into the microphone...'
                    : isCustomDataset
                    ? `Ask questions about ${selectedDataset?.name || 'this dataset'}...`
                    : 'Ask anything about sales, categories, revenue, delivery SLA, or top sellers...'
                }
                disabled={loading || isRecording}
                className="w-full bg-slate-50/70 border border-slate-200/80 rounded-xl pl-4 pr-32 py-3 text-xs sm:text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-all"
              />

              <div className="absolute right-2 flex items-center space-x-1.5">
                {/* Voice Input Button */}
                <button
                  type="button"
                  onClick={isRecording ? stopRecording : startRecording}
                  disabled={loading || isTranscribing}
                  className={`p-2 rounded-lg transition-colors cursor-pointer ${
                    isRecording
                      ? 'bg-rose-500 text-white animate-pulse'
                      : isTranscribing
                      ? 'bg-indigo-50 text-indigo-600'
                      : 'text-slate-400 hover:text-indigo-600 hover:bg-indigo-50'
                  }`}
                  title={
                    isRecording
                      ? 'Stop recording'
                      : isTranscribing
                      ? 'Transcribing audio...'
                      : 'Voice input (English / Hindi)'
                  }
                >
                  {isRecording ? (
                    <Square className="w-4 h-4" />
                  ) : isTranscribing ? (
                    <RefreshCw className="w-4 h-4 animate-spin text-indigo-600" />
                  ) : (
                    <Mic className="w-4 h-4" />
                  )}
                </button>

                {/* Submit Button */}
                <button
                  type="button"
                  onClick={() => handleAsk()}
                  disabled={loading || !question.trim()}
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white font-semibold rounded-lg text-xs shadow-xs transition cursor-pointer flex items-center space-x-1"
                >
                  {loading ? (
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <span>Ask AI</span>
                  )}
                </button>
              </div>
            </div>

            {/* Voice Notice */}
            {voiceNotice && (
              <div className="text-2xs text-indigo-700 bg-indigo-50 border border-indigo-100 rounded-lg p-2.5 flex items-center space-x-1.5">
                <CheckCircle2 className="w-3.5 h-3.5 text-indigo-500 shrink-0" />
                <span>{voiceNotice}</span>
              </div>
            )}
          </div>

          {/* Error Banner on 503 / 504 / Quota Limit */}
          {error && (
            <ErrorBanner
              message={error}
              onRetry={() => handleAsk()}
            />
          )}

          {/* AI Response Card */}
          {activeResponse && (
            <div className="border border-slate-200/80 rounded-xl bg-slate-50/50 divide-y divide-slate-100 overflow-hidden">
              {/* Header: Status + Privacy Badge */}
              <div className="px-5 py-3.5 bg-white flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center space-x-2">
                  <Sparkles className="w-4 h-4 text-indigo-600" />
                  <span className="font-bold text-xs text-slate-800">
                    Query Answer & Summary
                  </span>
                </div>

                <div className="flex items-center space-x-3">
                  {privacyBadge && (
                    <span className="px-2.5 py-0.5 rounded-full text-2xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                      {privacyBadge}
                    </span>
                  )}
                  <span className="text-2xs font-mono text-slate-400">
                    {isCustomDataset && datasetResponse?.execution_time_ms
                      ? `${datasetResponse.execution_time_ms.toFixed(0)}ms`
                      : ''}
                  </span>
                </div>
              </div>

              {/* Grounded Narrative or Deterministic Template Summary */}
              <div className="p-5 bg-white text-xs sm:text-sm text-slate-800 leading-relaxed font-sans">
                {activeResponse.explanation}
              </div>

              {/* Action Controls: Show SQL, Show Records */}
              <div className="px-5 py-2.5 bg-slate-50 flex items-center justify-between text-xs">
                {activeResponse.sql ? (
                  <button
                    onClick={() => setShowSql(!showSql)}
                    className="flex items-center space-x-1.5 font-semibold text-indigo-600 hover:text-indigo-800 transition cursor-pointer"
                  >
                    <Code className="w-3.5 h-3.5" />
                    <span>{showSql ? 'Hide SQL Query' : 'Show Generated SQL'}</span>
                    {showSql ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                  </button>
                ) : <div />}

                {rows.length > 0 && (
                  <button
                    onClick={() => setShowTable(!showTable)}
                    className="flex items-center space-x-1 font-semibold text-slate-600 hover:text-slate-900 transition cursor-pointer"
                  >
                    <TableIcon className="w-3.5 h-3.5" />
                    <span>{showTable ? 'Hide Table' : `Show Records (${rows.length})`}</span>
                  </button>
                )}
              </div>

              {/* SQL Code Block */}
              {showSql && activeResponse.sql && (
                <div className="p-4 bg-slate-900 text-xs font-mono text-emerald-400 overflow-x-auto shadow-inner">
                  <div className="text-slate-500 text-2xs mb-1">// Validated PostgreSQL SELECT</div>
                  <pre className="text-emerald-300 whitespace-pre-wrap">{activeResponse.sql}</pre>
                </div>
              )}

              {/* Suggested Chart */}
              {hasChartData && (
                <div className="p-5 bg-white">
                  <div className="flex items-center justify-between mb-3 text-xs">
                    <span className="font-bold text-slate-800 flex items-center space-x-1.5">
                      <BarChart2 className="w-3.5 h-3.5 text-indigo-600" />
                      <span>Data Visualization: {stringCol} vs {numericCol}</span>
                    </span>
                  </div>
                  <div className="h-56 w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={rows} margin={{ top: 10, right: 20, left: 20, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                        <XAxis dataKey={stringCol || 'label'} stroke="#94a3b8" fontSize={10} tickLine={false} />
                        <YAxis stroke="#94a3b8" fontSize={10} tickLine={false} />
                        <Tooltip />
                        <Bar dataKey={numericCol || 'value'} fill="#4f46e5" radius={[4, 4, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              )}

              {/* Data Rows Table (Plain text rendering, no raw HTML) */}
              {showTable && rows.length > 0 && (
                <div className="bg-white overflow-hidden">
                  <div className="overflow-x-auto max-h-64">
                    <table className="w-full text-left text-xs">
                      <thead className="bg-slate-50/70 text-slate-500 font-semibold border-b border-slate-200/60 uppercase tracking-wider text-2xs sticky top-0">
                        <tr>
                          {columns.map((col, idx) => (
                            <th key={idx} className="py-2 px-4 font-mono">{col}</th>
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
      )}

      {/* TAB 2: QUICK INSIGHTS & ANOMALIES */}
      {/* TAB 4: DASHBOARD (uploaded datasets only; Olist keeps its own pages) */}
      {isCustomDataset && activeTab === 'dashboard' && (
        <DatasetDashboard key={selectedDatasetId} datasetId={selectedDatasetId} />
      )}

      {isCustomDataset && activeTab === 'insights' && (
        <div className="space-y-6">
          <div className="flex items-center justify-between bg-white border border-slate-200/80 rounded-2xl p-4 shadow-xs">
            <div>
              <h2 className="text-sm font-bold text-slate-900">Pre-Computed Insights & Outliers</h2>
              <p className="text-xs text-slate-500">
                Deterministic time-trend, categorical rankings, distribution charts, and rolling MAD anomalies.
              </p>
            </div>
            <button
              onClick={() => loadQuickInsights(selectedDatasetId)}
              disabled={insightsLoading}
              className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-semibold flex items-center space-x-1.5 transition cursor-pointer"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${insightsLoading ? 'animate-spin' : ''}`} />
              <span>Refresh Insights</span>
            </button>
          </div>

          {insightsError && (
            <div className="p-4 bg-amber-50 text-amber-800 text-xs rounded-xl border border-amber-200">
              {insightsError}
            </div>
          )}

          {/* 3 Insight Charts */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
            {/* Chart 1: Time Trend */}
            <div className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-xs flex flex-col justify-between">
              <div>
                <div className="flex items-center space-x-2 text-indigo-600 mb-1">
                  <TrendingUp className="w-4 h-4" />
                  <span className="text-xs font-bold uppercase tracking-wider">Trend over Time</span>
                </div>
                <h3 className="text-xs font-bold text-slate-900 mb-3">
                  {insights?.time_trend?.title || 'Time Series Trend'}
                </h3>
              </div>

              {insights?.time_trend && insights.time_trend.data.length > 0 ? (
                <div className="h-48 w-full my-2">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={insights.time_trend.data}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                      <XAxis dataKey={insights.time_trend.x_axis} fontSize={9} stroke="#94a3b8" />
                      <YAxis fontSize={9} stroke="#94a3b8" />
                      <Tooltip />
                      <Line type="monotone" dataKey={insights.time_trend.y_axis} stroke="#4f46e5" strokeWidth={2} dot={{ r: 2 }} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <div className="h-48 flex items-center justify-center text-xs text-slate-400">
                  No date or time column available
                </div>
              )}

              {insights?.time_trend?.sql && (
                <div className="mt-3 p-2 bg-slate-900 rounded-lg text-2xs font-mono text-emerald-400 overflow-x-auto">
                  <pre className="whitespace-pre-wrap">{insights.time_trend.sql}</pre>
                </div>
              )}
            </div>

            {/* Chart 2: Top-N */}
            <div className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-xs flex flex-col justify-between">
              <div>
                <div className="flex items-center space-x-2 text-indigo-600 mb-1">
                  <BarChart2 className="w-4 h-4" />
                  <span className="text-xs font-bold uppercase tracking-wider">Top Rankings</span>
                </div>
                <h3 className="text-xs font-bold text-slate-900 mb-3">
                  {insights?.top_n?.title || 'Top Categories'}
                </h3>
              </div>

              {insights?.top_n && insights.top_n.data.length > 0 ? (
                <div className="h-48 w-full my-2">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={insights.top_n.data}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                      <XAxis dataKey={insights.top_n.x_axis} fontSize={9} stroke="#94a3b8" />
                      <YAxis fontSize={9} stroke="#94a3b8" />
                      <Tooltip />
                      <Bar dataKey={insights.top_n.y_axis} fill="#4f46e5" radius={[3, 3, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <div className="h-48 flex items-center justify-center text-xs text-slate-400">
                  No categorical dimensions available
                </div>
              )}

              {insights?.top_n?.sql && (
                <div className="mt-3 p-2 bg-slate-900 rounded-lg text-2xs font-mono text-emerald-400 overflow-x-auto">
                  <pre className="whitespace-pre-wrap">{insights.top_n.sql}</pre>
                </div>
              )}
            </div>

            {/* Chart 3: Distribution */}
            <div className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-xs flex flex-col justify-between">
              <div>
                <div className="flex items-center space-x-2 text-indigo-600 mb-1">
                  <PieChartIcon className="w-4 h-4" />
                  <span className="text-xs font-bold uppercase tracking-wider">Segment Distribution</span>
                </div>
                <h3 className="text-xs font-bold text-slate-900 mb-3">
                  {insights?.distribution?.title || 'Record Distribution'}
                </h3>
              </div>

              {insights?.distribution && insights.distribution.data.length > 0 ? (
                <div className="h-48 w-full my-2">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={insights.distribution.data}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                      <XAxis dataKey={insights.distribution.x_axis} fontSize={9} stroke="#94a3b8" />
                      <YAxis fontSize={9} stroke="#94a3b8" />
                      <Tooltip />
                      <Bar dataKey={insights.distribution.y_axis} fill="#0ea5e9" radius={[3, 3, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <div className="h-48 flex items-center justify-center text-xs text-slate-400">
                  No segment distribution available
                </div>
              )}

              {insights?.distribution?.sql && (
                <div className="mt-3 p-2 bg-slate-900 rounded-lg text-2xs font-mono text-emerald-400 overflow-x-auto">
                  <pre className="whitespace-pre-wrap">{insights.distribution.sql}</pre>
                </div>
              )}
            </div>
          </div>

          {/* Anomalies Table */}
          {insights && insights.anomalies && insights.anomalies.length > 0 && (
            <div className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-xs">
              <h3 className="text-xs font-bold text-slate-900 uppercase tracking-wider mb-3 flex items-center space-x-2 text-rose-600">
                <AlertCircle className="w-4 h-4" />
                <span>Statistical Outliers Detected ({insights.anomalies.length})</span>
              </h3>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs font-mono">
                  <thead className="bg-slate-50 text-slate-500 uppercase tracking-wider text-2xs">
                    <tr>
                      <th className="p-2.5">Period</th>
                      <th className="p-2.5">Metric</th>
                      <th className="p-2.5">Actual</th>
                      <th className="p-2.5">Expected</th>
                      <th className="p-2.5">Deviation</th>
                      <th className="p-2.5">Severity</th>
                      <th className="p-2.5">Direction</th>
                      <th className="p-2.5">Why?</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {insights.anomalies.map((anom, idx) => (
                      <tr key={idx} className="hover:bg-slate-50">
                        <td className="p-2.5">{anom.period}</td>
                        <td className="p-2.5">{anom.metric}</td>
                        <td className="p-2.5 font-bold">{anom.actual_value.toFixed(2)}</td>
                        <td className="p-2.5 text-slate-400">{anom.expected_value.toFixed(2)}</td>
                        <td className="p-2.5">{anom.deviation_pct.toFixed(1)}%</td>
                        <td className="p-2.5">
                          <span className={`px-2 py-0.5 rounded text-2xs font-bold ${
                            anom.severity === 'high' ? 'bg-rose-100 text-rose-700' : 'bg-amber-100 text-amber-700'
                          }`}>
                            {anom.severity}
                          </span>
                        </td>
                        <td className="p-2.5">{anom.direction}</td>
                        <td className="p-2.5">
                          <ExplainButton compact onClick={() => setExplainTarget({
                            source: { kind: 'dataset', datasetId: selectedDatasetId }, metric: null,
                            period: anom.period, grain: 'daily',
                          })} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* TAB 3: SEMANTIC LAYER REVIEW */}
      {isCustomDataset && activeTab === 'semantic' && (
        <div className="space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-white border border-slate-200/80 rounded-2xl p-5 shadow-xs">
            <div>
              <div className="flex items-center space-x-2">
                <h2 className="text-sm font-bold text-slate-900">Semantic Model Review</h2>
                <span className={`px-2 py-0.5 rounded text-2xs font-bold uppercase tracking-wider ${
                  semantic?.status === 'confirmed' ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'
                }`}>
                  {semantic?.status || 'draft'}
                </span>
              </div>
              <p className="text-xs text-slate-500 mt-1">
                Verify measures, dimensions, and relationship cardinalities used for AI Text-to-SQL queries.
              </p>
            </div>

            <button
              onClick={handleConfirmSemantic}
              disabled={semanticConfirming || semantic?.status === 'confirmed'}
              className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-xs font-semibold rounded-xl flex items-center space-x-1.5 transition cursor-pointer"
            >
              <Check className="w-4 h-4" />
              <span>{semantic?.status === 'confirmed' ? 'Model Confirmed' : 'Confirm Semantic Model'}</span>
            </button>
          </div>

          {semanticSuccessMsg && (
            <div className="p-3 bg-emerald-50 text-emerald-800 border border-emerald-200 rounded-xl text-xs flex items-center space-x-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-600" />
              <span>{semanticSuccessMsg}</span>
            </div>
          )}

          {/* Measures Table */}
          <div className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-xs">
            <h3 className="text-xs font-bold text-slate-900 uppercase tracking-wider mb-3">
              Measures ({semantic?.semantic_model.measures.length || 0})
            </h3>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs font-mono">
                <thead className="bg-slate-50 text-slate-500 uppercase tracking-wider text-2xs">
                  <tr>
                    <th className="p-2.5">Display Name</th>
                    <th className="p-2.5">Table</th>
                    <th className="p-2.5">Column</th>
                    <th className="p-2.5">Aggregation</th>
                    <th className="p-2.5">Synonyms</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {semantic?.semantic_model.measures.map((m, idx) => (
                    <tr key={idx} className="hover:bg-slate-50">
                      <td className="p-2.5 font-bold font-sans">{m.name}</td>
                      <td className="p-2.5">{m.table}</td>
                      <td className="p-2.5">{m.column || 'COUNT(*)'}</td>
                      <td className="p-2.5">
                        <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-700 text-2xs font-bold">
                          {m.aggregation}
                        </span>
                      </td>
                      <td className="p-2.5 text-slate-500 font-sans text-2xs">
                        {m.synonyms.join(', ') || '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Dimensions Table */}
          <div className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-xs">
            <h3 className="text-xs font-bold text-slate-900 uppercase tracking-wider mb-3">
              Dimensions ({semantic?.semantic_model.dimensions.length || 0})
            </h3>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs font-mono">
                <thead className="bg-slate-50 text-slate-500 uppercase tracking-wider text-2xs">
                  <tr>
                    <th className="p-2.5">Display Name</th>
                    <th className="p-2.5">Table</th>
                    <th className="p-2.5">Column</th>
                    <th className="p-2.5">Type</th>
                    <th className="p-2.5">Synonyms</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {semantic?.semantic_model.dimensions.map((d, idx) => (
                    <tr key={idx} className="hover:bg-slate-50">
                      <td className="p-2.5 font-bold font-sans">{d.name}</td>
                      <td className="p-2.5">{d.table}</td>
                      <td className="p-2.5">{d.column}</td>
                      <td className="p-2.5 text-slate-400">{d.data_type}</td>
                      <td className="p-2.5 text-slate-500 font-sans text-2xs">
                        {d.synonyms.join(', ') || '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
      <AnomalyExplainDrawer target={explainTarget} onClose={() => setExplainTarget(null)} />
    </div>
  );
};
