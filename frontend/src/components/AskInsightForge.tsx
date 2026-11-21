import React, { useState, useRef, useEffect } from 'react';
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
  Code,
  Mic,
  Square,
  Volume2,
  VolumeX,
  Languages,
  ShieldCheck,
  AlertCircle
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
  const [question, setQuestion] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [isDbUnavailable, setIsDbUnavailable] = useState<boolean>(false);
  const [response, setResponse] = useState<SQLAskResponse | null>(null);
  const [showSql, setShowSql] = useState<boolean>(false);
  const [showTable, setShowTable] = useState<boolean>(true);

  // Level 4 Voice & Multilingual State
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

  // Clean up recording timer on unmount
  useEffect(() => {
    return () => {
      if (timerIntervalRef.current) {
        window.clearInterval(timerIntervalRef.current);
      }
      if (window.speechSynthesis) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  const handleAsk = async (queryToAsk?: string) => {
    const targetQuestion = (queryToAsk !== undefined ? queryToAsk : question).trim();
    if (!targetQuestion) return;

    setQuestion(targetQuestion);
    setLoading(true);
    setError(null);
    setIsDbUnavailable(false);
    setShowSql(false);
    setVoiceNotice(null);

    // Stop speech synthesis if speaking previous answer
    if (window.speechSynthesis) {
      window.speechSynthesis.cancel();
      setIsSpeaking(false);
    }

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

  // --------------------------------------------------------------------------
  // Voice Recording & Transcription
  // --------------------------------------------------------------------------
  const startRecording = async () => {
    setVoiceNotice(null);
    setError(null);

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setVoiceNotice('Microphone audio recording is not supported in this browser.');
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunksRef.current = [];

      let mimeType = 'audio/webm';
      if (!MediaRecorder.isTypeSupported('audio/webm')) {
        if (MediaRecorder.isTypeSupported('audio/ogg')) {
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
        // Stop audio tracks
        stream.getTracks().forEach((track) => track.stop());

        if (timerIntervalRef.current) {
          window.clearInterval(timerIntervalRef.current);
          timerIntervalRef.current = null;
        }
        setIsRecording(false);

        const audioBlob = new Blob(audioChunksRef.current, {
          type: recorder.mimeType || 'audio/webm'
        });

        if (audioBlob.size === 0) {
          setVoiceNotice('No audio data captured. Please try recording again.');
          return;
        }

        await processAudioTranscription(audioBlob);
      };

      recorder.start(250); // collect chunks every 250ms
      setIsRecording(true);
      setRecordingSeconds(0);

      // Start duration counter (capped at 60s)
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
      console.error('Microphone error:', err);
      if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
        setVoiceNotice('Microphone access was denied. Please allow microphone permissions in your browser to use voice input.');
      } else {
        setVoiceNotice(`Unable to access microphone: ${err.message || 'Unknown error'}`);
      }
      setIsRecording(false);
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
    }
  };

  const processAudioTranscription = async (blob: Blob) => {
    setIsTranscribing(true);
    setVoiceNotice(null);

    try {
      const result = await api.transcribeVoice(blob, 'voice_query.webm');
      if (result.text) {
        // Put transcript in editable input box (never auto-send)
        setQuestion(result.text);
        const langLabel = result.detected_language === 'hi' ? 'Hindi (हिन्दी)' : (result.detected_language === 'hinglish' ? 'Hinglish' : 'English');
        setVoiceNotice(`Transcribed in ${langLabel} (${(result.confidence * 100).toFixed(0)}% confidence). You can review and edit your question below before querying.`);
      } else {
        setVoiceNotice('Transcription did not return any speech text. Please try again.');
      }
    } catch (err: any) {
      console.warn('Backend transcription failed; attempting browser SpeechRecognition fallback:', err);
      fallbackBrowserSpeechRecognition();
    } finally {
      setIsTranscribing(false);
    }
  };

  // Fallback: Browser Web Speech API (hi-IN / en-IN)
  const fallbackBrowserSpeechRecognition = () => {
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setVoiceNotice('Backend transcription unavailable (ensure GEMINI_API_KEY is configured), and browser Web Speech API is unsupported.');
      return;
    }

    try {
      const recognition = new SpeechRecognition();
      recognition.lang = selectedLanguage === 'hi' ? 'hi-IN' : 'en-IN';
      recognition.interimResults = false;
      recognition.maxAlternatives = 1;

      setVoiceNotice(`Backend service unavailable. Using browser speech recognition (${recognition.lang})...`);

      recognition.onresult = (event: any) => {
        const transcript = event.results[0][0].transcript;
        if (transcript) {
          setQuestion(transcript);
          setVoiceNotice('Voice captured via browser Web Speech API. You can review or edit before sending.');
        }
      };

      recognition.onerror = (e: any) => {
        setVoiceNotice(`Browser speech recognition error: ${e.error || 'Failed'}`);
      };

      recognition.start();
    } catch (e: any) {
      setVoiceNotice(`Speech recognition failed: ${e.message}`);
    }
  };

  // --------------------------------------------------------------------------
  // Read Aloud (speechSynthesis)
  // --------------------------------------------------------------------------
  const handleReadAloud = (textToRead: string, langCode?: string) => {
    if (!('speechSynthesis' in window)) {
      setSpeechWarning('Speech synthesis is not supported in this browser.');
      return;
    }

    if (isSpeaking) {
      window.speechSynthesis.cancel();
      setIsSpeaking(false);
      return;
    }

    setSpeechWarning(null);
    const utterance = new SpeechSynthesisUtterance(textToRead.replace(/\*\*/g, ''));

    // Check available system voices
    const voices = window.speechSynthesis.getVoices();
    const isHindi = langCode === 'hi' || langCode === 'hinglish';

    if (isHindi) {
      const hindiVoice = voices.find((v) => v.lang.startsWith('hi') || v.lang.includes('Hindi'));
      if (hindiVoice) {
        utterance.voice = hindiVoice;
        utterance.lang = 'hi-IN';
      } else {
        setSpeechWarning('No native Hindi voice installed on this system; playing using default system voice.');
        utterance.lang = 'en-IN';
      }
    } else {
      const englishVoice = voices.find((v) => v.lang.startsWith('en-IN') || v.lang.startsWith('en'));
      if (englishVoice) {
        utterance.voice = englishVoice;
      }
      utterance.lang = 'en-US';
    }

    utterance.onend = () => setIsSpeaking(false);
    utterance.onerror = () => setIsSpeaking(false);

    setIsSpeaking(true);
    window.speechSynthesis.speak(utterance);
  };

  // Helper formatting timer string (MM:SS)
  const formatTimer = (totalSeconds: number) => {
    const mins = Math.floor(totalSeconds / 60);
    const secs = totalSeconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
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

  const rows = response?.rows || [];
  const columns = response?.columns || (rows.length > 0 ? Object.keys(rows[0]) : []);
  const stringCol = columns.find((c) => rows.some((r) => typeof r[c] === 'string')) || columns[0];
  const numericCol = columns.find((c) => rows.some((r) => typeof r[c] === 'number' && !c.toLowerCase().includes('id')));
  const hasChartData = Boolean(numericCol && stringCol && rows.length > 0 && rows.length <= 50);
  const chartType = response?.suggested_chart || (stringCol?.toLowerCase().includes('month') || stringCol?.toLowerCase().includes('date') ? 'line' : 'bar');

  return (
    <div className="bg-white border border-slate-200/80 rounded-2xl p-6 shadow-xs transition-all font-sans">
      {/* Top Controls: Language Selector & Audio Notice */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div className="flex items-center space-x-2">
          <div className="flex items-center space-x-1.5 text-xs text-slate-500 font-medium">
            <Languages className="w-3.5 h-3.5 text-indigo-500" />
            <span>Voice & Question Language:</span>
          </div>
          <div className="inline-flex rounded-lg border border-slate-200 bg-slate-50 p-0.5 text-xs">
            <button
              onClick={() => setSelectedLanguage('auto')}
              className={`px-2.5 py-1 rounded-md font-medium transition cursor-pointer ${
                selectedLanguage === 'auto'
                  ? 'bg-white text-indigo-600 shadow-2xs font-semibold'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Auto (स्वचालित)
            </button>
            <button
              onClick={() => setSelectedLanguage('hi')}
              className={`px-2.5 py-1 rounded-md font-medium transition cursor-pointer font-devanagari ${
                selectedLanguage === 'hi'
                  ? 'bg-white text-indigo-600 shadow-2xs font-semibold'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              हिन्दी (Hindi)
            </button>
            <button
              onClick={() => setSelectedLanguage('en')}
              className={`px-2.5 py-1 rounded-md font-medium transition cursor-pointer ${
                selectedLanguage === 'en'
                  ? 'bg-white text-indigo-600 shadow-2xs font-semibold'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              English
            </button>
          </div>
        </div>

        <div className="flex items-center space-x-1 text-2xs text-slate-400">
          <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" />
          <span>Audio is sent to Google Gemini for transcription and is not stored.</span>
        </div>
      </div>

      {/* Input Bar with Mic Recording and Ask Button */}
      <div className="relative mb-3">
        <div className="flex gap-2">
          <div className="relative flex-1">
            <input
              type="text"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                selectedLanguage === 'hi'
                  ? 'हिन्दी या हिंग्लिश में कोई भी व्यावसायिक प्रश्न पूछें (उदा. सबसे ज्यादा बिक्री किस श्रेणी में हुई?)...'
                  : 'Ask any business question in English, Hindi (Devanagari), or Hinglish...'
              }
              disabled={loading || isTranscribing}
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

          {/* Mic Record / Stop Button */}
          {isRecording ? (
            <button
              onClick={stopRecording}
              className="flex items-center space-x-2 bg-red-600 hover:bg-red-700 text-white font-semibold text-xs px-4 py-3.5 rounded-xl transition-all shadow-xs cursor-pointer animate-pulse"
              title="Click to stop recording"
            >
              <Square className="w-4 h-4 fill-white" />
              <span>{formatTimer(recordingSeconds)} / 01:00</span>
            </button>
          ) : (
            <button
              onClick={startRecording}
              disabled={loading || isTranscribing}
              className="flex items-center space-x-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 font-semibold text-xs px-3.5 py-3.5 rounded-xl border border-slate-200/80 transition-all disabled:opacity-50 cursor-pointer"
              title="Click to record voice in Hindi, Hinglish, or English"
            >
              {isTranscribing ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin text-indigo-600" />
                  <span className="hidden sm:inline">Transcribing...</span>
                </>
              ) : (
                <>
                  <Mic className="w-4 h-4 text-indigo-600" />
                  <span className="hidden sm:inline">Voice</span>
                </>
              )}
            </button>
          )}

          {/* Ask AI Submit Button */}
          <button
            onClick={() => handleAsk()}
            disabled={loading || isRecording || isTranscribing || !question.trim()}
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

      {/* Voice Notice or Informational Feedback */}
      {voiceNotice && (
        <div className="mb-4 text-xs bg-indigo-50/80 text-indigo-800 border border-indigo-200/70 rounded-xl px-4 py-2.5 flex items-center justify-between">
          <span>{voiceNotice}</span>
          <button onClick={() => setVoiceNotice(null)} className="text-indigo-400 hover:text-indigo-700 ml-2 font-bold cursor-pointer">
            ✕
          </button>
        </div>
      )}

      {/* Example Prompt Pills */}
      <div className="mb-6">
        <div className="flex items-center space-x-1.5 text-xs text-slate-500 mb-2 font-medium">
          <HelpCircle className="w-3.5 h-3.5 text-indigo-500" />
          <span>Try asking these example prompts:</span>
        </div>
        <div className="flex flex-wrap gap-2">
          {(selectedLanguage === 'hi'
            ? EXAMPLE_QUESTIONS.hi
            : selectedLanguage === 'en'
            ? EXAMPLE_QUESTIONS.en
            : [...EXAMPLE_QUESTIONS.en.slice(0, 3), ...EXAMPLE_QUESTIONS.hi.slice(0, 2), ...EXAMPLE_QUESTIONS.hinglish.slice(0, 2)]
          ).map((q, idx) => (
            <button
              key={idx}
              onClick={() => handleAsk(q)}
              disabled={loading || isRecording}
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
            title={isDbUnavailable ? 'Database Unavailable' : 'Query Processing Error'}
            message={error}
            onRetry={() => handleAsk()}
          />
        </div>
      )}

      {/* Loading Skeleton */}
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
              {response.language && (
                <span className="text-2xs bg-slate-100 text-slate-600 border border-slate-200 px-2 py-0.5 rounded-md font-mono">
                  {response.language === 'hi' ? 'हिन्दी' : response.language === 'hinglish' ? 'Hinglish' : 'English'}
                </span>
              )}
            </div>

            <div className="flex items-center space-x-2">
              <span
                className={`text-[11px] px-2.5 py-0.5 rounded-full font-medium border ${
                  response.route === 'intent'
                    ? 'bg-blue-50 text-blue-700 border-blue-200'
                    : 'bg-indigo-50 text-indigo-700 border-indigo-200'
                }`}
              >
                {response.route === 'intent' ? 'Deterministic Intent Router' : 'Guarded Text-to-SQL'}
              </span>

              {response.grounding_verified && (
                <span className="text-[11px] bg-emerald-50 text-emerald-700 border border-emerald-200 px-2 py-0.5 rounded-full flex items-center space-x-1 font-medium">
                  <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                  <span>Grounding Verified</span>
                </span>
              )}

              {/* Read Aloud Button */}
              <button
                onClick={() => handleReadAloud(response.explanation, response.language)}
                className={`text-[11px] px-2.5 py-0.5 rounded-full border flex items-center space-x-1 font-medium transition cursor-pointer ${
                  isSpeaking
                    ? 'bg-indigo-600 text-white border-indigo-600'
                    : 'bg-slate-100 hover:bg-slate-200 text-slate-700 border-slate-200'
                }`}
                title="Read answer aloud"
              >
                {isSpeaking ? (
                  <>
                    <VolumeX className="w-3 h-3" />
                    <span>Stop Voice</span>
                  </>
                ) : (
                  <>
                    <Volume2 className="w-3 h-3" />
                    <span>Read Aloud</span>
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Speech Warning (e.g. no Hindi voice installed) */}
          {speechWarning && (
            <div className="mx-5 text-2xs bg-amber-50 text-amber-800 border border-amber-200 px-3 py-1.5 rounded-lg flex items-center space-x-1">
              <AlertCircle className="w-3 h-3 text-amber-600" />
              <span>{speechWarning}</span>
            </div>
          )}

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
