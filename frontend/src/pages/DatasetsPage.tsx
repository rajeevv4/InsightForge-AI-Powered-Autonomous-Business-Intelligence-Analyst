import React, { useState, useEffect, useRef } from 'react';
import {
  Database,
  Upload,
  AlertTriangle,
  CheckCircle2,
  Trash2,
  Eye,
  Shield,
  Layers,
  Sparkles,
  RefreshCw,
  Clock,
  ArrowRight,
  HelpCircle,
  FileText,
  X,
  ExternalLink
} from 'lucide-react';
import { api } from '../services/api';
import {
  DatasetSummary,
  DatasetProfile,
  TableProfile,
  ColumnProfile,
  TablePreviewResponse
} from '../types/api';

export const DatasetsPage: React.FC = () => {
  const [datasets, setDatasets] = useState<DatasetSummary[]>([]);
  const [selectedDatasetId, setSelectedDatasetId] = useState<string>('00000000-0000-0000-0000-000000000001');
  const [profile, setProfile] = useState<DatasetProfile | null>(null);
  const [activeTableIndex, setActiveTableIndex] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(true);
  const [profileLoading, setProfileLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Upload modal state
  const [uploadModalOpen, setUploadModalOpen] = useState<boolean>(false);
  const [uploadFiles, setUploadFiles] = useState<File[]>([]);
  const [uploadDatasetName, setUploadDatasetName] = useState<string>('');
  const [uploadShareSamples, setUploadShareSamples] = useState<boolean>(false);
  const [uploading, setUploading] = useState<boolean>(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Preview modal state
  const [previewOpen, setPreviewOpen] = useState<boolean>(false);
  const [previewData, setPreviewData] = useState<TablePreviewResponse | null>(null);
  const [previewLoading, setPreviewLoading] = useState<boolean>(false);

  // Load datasets list
  const loadDatasets = async (selectId?: string) => {
    try {
      setLoading(true);
      setError(null);
      const data = await api.getDatasets();
      setDatasets(data);
      if (data.length > 0) {
        const targetId = selectId || (data.some(d => d.id === selectedDatasetId) ? selectedDatasetId : data[0].id);
        setSelectedDatasetId(targetId);
      }
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to load datasets list.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDatasets();
  }, []);

  // Load selected dataset profile
  useEffect(() => {
    if (!selectedDatasetId) return;
    const fetchProfile = async () => {
      try {
        setProfileLoading(true);
        const data = await api.getDatasetProfile(selectedDatasetId);
        setProfile(data);
        setActiveTableIndex(0);
      } catch (err: any) {
        setError(err?.response?.data?.detail || 'Failed to fetch dataset profile.');
      } finally {
        setProfileLoading(false);
      }
    };
    fetchProfile();
  }, [selectedDatasetId]);

  // Handle file drop / selection
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const selected = Array.from(e.target.files).slice(0, 5);
      setUploadFiles(selected);
      if (!uploadDatasetName && selected.length > 0) {
        const defaultName = selected[0].name.split('.')[0].replace(/[-_]/g, ' ');
        setUploadDatasetName(defaultName.charAt(0).toUpperCase() + defaultName.slice(1));
      }
    }
  };

  const handleUploadSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (uploadFiles.length === 0) {
      setUploadError('Please select at least 1 file (CSV, TSV, or XLSX).');
      return;
    }
    try {
      setUploading(true);
      setUploadError(null);
      const res = await api.uploadDataset(uploadFiles, uploadDatasetName, uploadShareSamples);
      setUploadModalOpen(false);
      setUploadFiles([]);
      setUploadDatasetName('');
      setUploadShareSamples(false);
      await loadDatasets(res.dataset_id);
    } catch (err: any) {
      setUploadError(err?.response?.data?.detail || 'Failed to upload and profile dataset.');
    } finally {
      setUploading(false);
    }
  };

  // Handle table preview
  const handlePreviewTable = async (tableName: string) => {
    if (!profile) return;
    try {
      setPreviewLoading(true);
      setPreviewOpen(true);
      const data = await api.previewDatasetTable(profile.id, tableName, 50);
      setPreviewData(data);
    } catch (err: any) {
      alert(err?.response?.data?.detail || 'Failed to preview table.');
      setPreviewOpen(false);
    } finally {
      setPreviewLoading(false);
    }
  };

  // Handle column role change
  const handleRoleChange = async (tableName: string, colName: string, newRole: string) => {
    if (!profile || profile.is_demo) return;
    try {
      const updated = await api.updateDataset(profile.id, {
        column_updates: [{ table_name: tableName, column_name: colName, role: newRole }]
      });
      setProfile(updated);
    } catch (err: any) {
      alert(err?.response?.data?.detail || 'Failed to update column role.');
    }
  };

  // Handle toggle relationship confirmation
  const handleToggleRelationship = async (relIndex: number) => {
    if (!profile || profile.is_demo) return;
    const rel = profile.relationships[relIndex];
    try {
      const updated = await api.updateDataset(profile.id, {
        confirmed_relationships: [{
          parent_table: rel.parent_table,
          parent_column: rel.parent_column,
          child_table: rel.child_table,
          child_column: rel.child_column,
          confirmed: !rel.confirmed
        }]
      });
      setProfile(updated);
    } catch (err: any) {
      alert(err?.response?.data?.detail || 'Failed to update relationship.');
    }
  };

  // Handle toggle share samples
  const handleToggleShareSamples = async () => {
    if (!profile || profile.is_demo) return;
    try {
      const updated = await api.updateDataset(profile.id, {
        share_samples: !profile.share_samples
      });
      setProfile(updated);
    } catch (err: any) {
      alert(err?.response?.data?.detail || 'Failed to toggle share samples.');
    }
  };

  // Handle delete dataset
  const handleDeleteDataset = async () => {
    if (!profile || profile.is_demo) return;
    if (!window.confirm(`Are you sure you want to permanently delete '${profile.name}' and drop schema '${profile.schema_name}'?`)) {
      return;
    }
    try {
      setLoading(true);
      await api.deleteDataset(profile.id);
      await loadDatasets();
    } catch (err: any) {
      alert(err?.response?.data?.detail || 'Failed to delete dataset.');
      setLoading(false);
    }
  };

  const currentTable: TableProfile | undefined = profile?.tables?.[activeTableIndex];

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-6">
      {/* Top Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-3">
            <div className="p-2.5 bg-blue-50 text-blue-600 rounded-xl">
              <Database className="w-6 h-6" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Dataset Workspace</h1>
              <p className="text-sm text-slate-500">
                Upload tabular files (CSV, TSV, XLSX) into isolated schemas with deterministic zero-LLM profiling.
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center space-x-3">
          <button
            onClick={() => loadDatasets(selectedDatasetId)}
            className="p-2 text-slate-500 hover:text-slate-800 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 transition shadow-sm"
            title="Refresh Datasets"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
          <button
            onClick={() => setUploadModalOpen(true)}
            className="flex items-center space-x-2 px-4 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition shadow-sm"
          >
            <Upload className="w-4 h-4" />
            <span>Upload Dataset</span>
          </button>
        </div>
      </div>

      {/* Error alert */}
      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-red-700 text-sm flex items-start space-x-3">
          <AlertTriangle className="w-5 h-5 flex-shrink-0 text-red-600 mt-0.5" />
          <div>
            <div className="font-semibold">Dataset Notice</div>
            <div>{error}</div>
          </div>
        </div>
      )}

      {/* Dataset Picker Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {datasets.map((ds) => {
          const isSelected = ds.id === selectedDatasetId;
          return (
            <div
              key={ds.id}
              onClick={() => setSelectedDatasetId(ds.id)}
              className={`p-4 rounded-xl border cursor-pointer transition relative ${
                isSelected
                  ? 'bg-blue-50/50 border-blue-500 ring-2 ring-blue-500/20 shadow-sm'
                  : 'bg-white border-slate-200 hover:border-slate-300 hover:shadow-sm'
              }`}
            >
              <div className="flex items-start justify-between">
                <div className="flex items-center space-x-2">
                  <span className="font-semibold text-slate-900 truncate max-w-[150px]">{ds.name}</span>
                  {ds.is_demo && (
                    <span className="px-1.5 py-0.5 text-xs font-semibold bg-emerald-100 text-emerald-800 rounded">
                      Demo
                    </span>
                  )}
                </div>
                <span className="text-xs px-2 py-0.5 font-mono bg-slate-100 text-slate-600 rounded">
                  {ds.schema_name}
                </span>
              </div>

              <div className="mt-3 flex items-center justify-between text-xs text-slate-500">
                <span>{ds.table_count} table{ds.table_count !== 1 ? 's' : ''}</span>
                <span>{ds.total_rows.toLocaleString()} rows</span>
              </div>

              {ds.expires_at && (
                <div className="mt-2 flex items-center space-x-1 text-xs text-amber-600 font-medium">
                  <Clock className="w-3.5 h-3.5" />
                  <span>Expires in 24h</span>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Dataset Detail View */}
      {profileLoading ? (
        <div className="p-12 text-center text-slate-400 bg-white rounded-xl border border-slate-200">
          <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-blue-500" />
          <p>Profiling dataset and analyzing relationships...</p>
        </div>
      ) : profile ? (
        <div className="space-y-6">
          {/* Metadata Toolbar */}
          <div className="bg-white p-5 rounded-xl border border-slate-200 flex flex-col md:flex-row md:items-center justify-between gap-4 shadow-sm">
            <div className="flex flex-wrap items-center gap-3">
              <span className="text-lg font-bold text-slate-900">{profile.name}</span>
              <span className="px-2.5 py-1 text-xs font-mono font-medium bg-slate-100 text-slate-700 rounded-md border border-slate-200">
                Schema: {profile.schema_name}
              </span>
              <span className="px-2.5 py-1 text-xs font-medium bg-green-50 text-green-700 rounded-md border border-green-200">
                Status: {profile.status}
              </span>
              {profile.is_demo && (
                <span className="px-2.5 py-1 text-xs font-medium bg-purple-50 text-purple-700 rounded-md border border-purple-200">
                  Read-Only Built-In
                </span>
              )}
            </div>

            <div className="flex items-center space-x-4">
              {/* Privacy Toggle: Share with AI */}
              {!profile.is_demo && (
                <label className="flex items-center space-x-2.5 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={profile.share_samples}
                    onChange={handleToggleShareSamples}
                    className="rounded border-slate-300 text-blue-600 focus:ring-blue-500 w-4 h-4"
                  />
                  <span className="text-xs font-medium text-slate-700 flex items-center space-x-1">
                    <Shield className="w-3.5 h-3.5 text-slate-500" />
                    <span>Share samples with AI</span>
                  </span>
                </label>
              )}

              {!profile.is_demo && (
                <button
                  onClick={handleDeleteDataset}
                  className="flex items-center space-x-1.5 px-3 py-1.5 text-xs font-medium text-red-600 hover:text-red-700 hover:bg-red-50 rounded-lg transition border border-red-200"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  <span>Delete</span>
                </button>
              )}
            </div>
          </div>

          {/* Privacy Disclaimer Banner */}
          <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-600 flex items-start space-x-3">
            <Shield className="w-4 h-4 text-blue-600 mt-0.5 flex-shrink-0" />
            <div>
              <span className="font-semibold text-slate-800">Privacy & Tenancy Guarantee: </span>
              Each upload is isolated in its own PostgreSQL schema (<code className="bg-slate-200 px-1 rounded">{profile.schema_name}</code>).
              {profile.share_samples ? (
                <span className="text-amber-800 ml-1">
                  Sample values mode is ENABLED: up to 5 distinct values per dimension may be used for AI query context. Raw cell data is never stored outside your schema.
                </span>
              ) : (
                <span className="ml-1">
                  Sample values mode is DISABLED: Zero row or cell data is shared with language models. Queries run purely from column names and statistical types.
                </span>
              )}
            </div>
          </div>

          {/* Inferred Relationships Card (if any) */}
          {profile.relationships && profile.relationships.length > 0 && (
            <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm space-y-3">
              <div className="flex items-center space-x-2 text-sm font-bold text-slate-900">
                <Layers className="w-4 h-4 text-indigo-600" />
                <span>Inferred Cross-Table Relationships ({profile.relationships.length})</span>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {profile.relationships.map((rel, idx) => (
                  <div
                    key={idx}
                    className="p-3.5 bg-slate-50/70 border border-slate-200 rounded-lg flex items-center justify-between text-xs"
                  >
                    <div className="flex items-center space-x-2">
                      <span className="font-mono font-semibold text-slate-800">{rel.parent_table}.{rel.parent_column}</span>
                      <ArrowRight className="w-3.5 h-3.5 text-slate-400" />
                      <span className="font-mono font-semibold text-slate-800">{rel.child_table}.{rel.child_column}</span>
                      <span className="px-1.5 py-0.5 bg-indigo-50 text-indigo-700 font-bold rounded">
                        {rel.cardinality}
                      </span>
                      <span className="text-slate-400">({Math.round(rel.confidence * 100)}% match)</span>
                    </div>

                    {!profile.is_demo && (
                      <button
                        onClick={() => handleToggleRelationship(idx)}
                        className={`px-2 py-1 rounded text-xs font-semibold transition ${
                          rel.confirmed
                            ? 'bg-emerald-100 text-emerald-800 border border-emerald-200'
                            : 'bg-white text-slate-600 border border-slate-200 hover:bg-slate-100'
                        }`}
                      >
                        {rel.confirmed ? 'Confirmed ✓' : 'Confirm'}
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Table Tabs & Detail */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
            {/* Table Selector Tabs */}
            <div className="flex items-center border-b border-slate-200 bg-slate-50/50 px-4 overflow-x-auto">
              {profile.tables.map((tbl, idx) => (
                <button
                  key={tbl.safe_name}
                  onClick={() => setActiveTableIndex(idx)}
                  className={`py-3 px-4 text-xs font-semibold border-b-2 whitespace-nowrap transition flex items-center space-x-2 ${
                    activeTableIndex === idx
                      ? 'border-blue-600 text-blue-600 bg-white'
                      : 'border-transparent text-slate-500 hover:text-slate-800'
                  }`}
                >
                  <FileText className="w-3.5 h-3.5" />
                  <span>{tbl.safe_name}</span>
                  <span className="px-1.5 py-0.5 text-[10px] bg-slate-200/80 text-slate-700 rounded-full">
                    {tbl.row_count.toLocaleString()} rows
                  </span>
                </button>
              ))}
            </div>

            {currentTable && (
              <div className="p-6 space-y-6">
                {/* Table Header Info */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-100">
                  <div className="space-y-1">
                    <div className="flex items-center space-x-3">
                      <h2 className="text-lg font-bold text-slate-900">{currentTable.safe_name}</h2>
                      <span className="text-xs text-slate-500">(Source: {currentTable.original_name})</span>
                    </div>
                    <div className="flex flex-wrap items-center gap-3 text-xs text-slate-600">
                      <span><strong>{currentTable.row_count.toLocaleString()}</strong> rows</span>
                      <span>•</span>
                      <span><strong>{currentTable.column_count}</strong> columns</span>
                      {currentTable.candidate_pk && (
                        <>
                          <span>•</span>
                          <span>Candidate PK: <code className="font-mono font-bold text-blue-700">{currentTable.candidate_pk}</code></span>
                        </>
                      )}
                      {currentTable.candidate_time_column && (
                        <>
                          <span>•</span>
                          <span>Time Column: <code className="font-mono font-bold text-amber-700">{currentTable.candidate_time_column}</code></span>
                        </>
                      )}
                    </div>
                  </div>

                  <button
                    onClick={() => handlePreviewTable(currentTable.safe_name)}
                    className="flex items-center space-x-1.5 px-3.5 py-2 text-xs font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg transition"
                  >
                    <Eye className="w-3.5 h-3.5 text-slate-600" />
                    <span>Preview Data (50 rows)</span>
                  </button>
                </div>

                {/* Quality Findings for Table */}
                {currentTable.quality_findings && currentTable.quality_findings.length > 0 && (
                  <div className="p-4 bg-amber-50/70 border border-amber-200 rounded-xl space-y-2">
                    <div className="flex items-center space-x-2 text-xs font-bold text-amber-900">
                      <AlertTriangle className="w-4 h-4 text-amber-600" />
                      <span>Data Quality Findings ({currentTable.quality_findings.length})</span>
                    </div>
                    <div className="space-y-1.5 text-xs text-amber-800">
                      {currentTable.quality_findings.map((f, i) => (
                        <div key={i} className="flex items-start space-x-2">
                          <span className="font-semibold capitalize">• [{f.type.replace(/_/g, ' ')}]</span>
                          <span>{f.message || f.description}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Columns Table */}
                <div className="overflow-x-auto rounded-lg border border-slate-200">
                  <table className="w-full text-left border-collapse text-xs">
                    <thead>
                      <tr className="bg-slate-50 border-b border-slate-200 text-slate-600 font-semibold uppercase tracking-wider">
                        <th className="py-2.5 px-3">Column Name</th>
                        <th className="py-2.5 px-3">PostgreSQL Type</th>
                        <th className="py-2.5 px-3">Analytical Role</th>
                        <th className="py-2.5 px-3">Null %</th>
                        <th className="py-2.5 px-3">Distinct</th>
                        <th className="py-2.5 px-3">Range / Samples</th>
                        <th className="py-2.5 px-3">Description</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 font-mono">
                      {currentTable.columns.map((col) => (
                        <tr key={col.safe_name} className="hover:bg-slate-50/60 transition">
                          <td className="py-2.5 px-3 font-semibold text-slate-900">
                            {col.safe_name}
                            {col.original_name !== col.safe_name && (
                              <span className="block font-sans text-[10px] text-slate-400">
                                was: {col.original_name}
                              </span>
                            )}
                          </td>
                          <td className="py-2.5 px-3 text-slate-600 font-sans">
                            <span className="px-1.5 py-0.5 bg-slate-100 rounded text-slate-700">
                              {col.pg_type}
                            </span>
                          </td>
                          <td className="py-2.5 px-3 font-sans">
                            {profile.is_demo ? (
                              <span className="px-2 py-0.5 text-xs font-semibold rounded bg-slate-100 text-slate-700">
                                {col.role}
                              </span>
                            ) : (
                              <select
                                value={col.role}
                                onChange={(e) => handleRoleChange(currentTable.safe_name, col.safe_name, e.target.value)}
                                className="text-xs bg-white border border-slate-200 rounded px-2 py-1 font-medium focus:ring-1 focus:ring-blue-500"
                              >
                                <option value="id">id</option>
                                <option value="datetime">datetime</option>
                                <option value="measure">measure</option>
                                <option value="dimension">dimension</option>
                                <option value="boolean">boolean</option>
                                <option value="free_text">free_text</option>
                              </select>
                            )}
                          </td>
                          <td className="py-2.5 px-3 font-sans text-slate-600">
                            <div className="flex items-center space-x-1.5">
                              <span>{col.null_pct}%</span>
                              {col.null_pct > 20 && (
                                <span className="w-1.5 h-1.5 rounded-full bg-amber-500" title="High nulls" />
                              )}
                            </div>
                          </td>
                          <td className="py-2.5 px-3 font-sans text-slate-600">
                            {col.distinct_count.toLocaleString()}
                          </td>
                          <td className="py-2.5 px-3 font-sans text-slate-500 text-[11px] max-w-[200px] truncate">
                            {col.min_val && col.max_val ? (
                              <span>[{col.min_val} ... {col.max_val}]</span>
                            ) : (
                              <span>—</span>
                            )}
                          </td>
                          <td className="py-2.5 px-3 font-sans text-slate-500">
                            {col.user_description || <span className="text-slate-300 italic">None</span>}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        </div>
      ) : null}

      {/* Upload Modal */}
      {uploadModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
          <div className="bg-white rounded-2xl max-w-lg w-full p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between border-b pb-3">
              <h3 className="text-lg font-bold text-slate-900">Upload Tabular Dataset</h3>
              <button
                onClick={() => setUploadModalOpen(false)}
                className="text-slate-400 hover:text-slate-600"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {uploadError && (
              <div className="p-3 bg-red-50 border border-red-200 text-red-700 text-xs rounded-lg">
                {uploadError}
              </div>
            )}

            <form onSubmit={handleUploadSubmit} className="space-y-4 text-xs">
              <div>
                <label className="block font-semibold text-slate-700 mb-1">Dataset Name (Optional)</label>
                <input
                  type="text"
                  placeholder="e.g. Q3 Sales & Customers"
                  value={uploadDatasetName}
                  onChange={(e) => setUploadDatasetName(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg text-xs focus:ring-1 focus:ring-blue-500"
                />
              </div>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">Files (1 to 5: CSV, TSV, XLSX)</label>
                <div
                  onClick={() => fileInputRef.current?.click()}
                  className="border-2 border-dashed border-slate-300 hover:border-blue-500 rounded-xl p-6 text-center cursor-pointer transition bg-slate-50/50"
                >
                  <Upload className="w-8 h-8 text-slate-400 mx-auto mb-2" />
                  <p className="font-medium text-slate-700">Click to select files</p>
                  <p className="text-[11px] text-slate-400 mt-1">Accepts CSV, TSV, or XLSX up to 25 MB</p>
                  <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    accept=".csv,.tsv,.xlsx"
                    onChange={handleFileChange}
                    className="hidden"
                  />
                </div>

                {uploadFiles.length > 0 && (
                  <div className="mt-2 space-y-1">
                    <span className="font-semibold text-slate-700">Selected files ({uploadFiles.length}):</span>
                    {uploadFiles.map((f, i) => (
                      <div key={i} className="flex items-center justify-between p-1.5 bg-slate-100 rounded text-slate-700">
                        <span>{f.name}</span>
                        <span>{(f.size / (1024 * 1024)).toFixed(2)} MB</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="p-3 bg-blue-50/60 border border-blue-100 rounded-lg space-y-1">
                <label className="flex items-center space-x-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={uploadShareSamples}
                    onChange={(e) => setUploadShareSamples(e.target.checked)}
                    className="rounded text-blue-600 focus:ring-blue-500"
                  />
                  <span className="font-semibold text-blue-900">Share sample values with AI</span>
                </label>
                <p className="text-[11px] text-blue-700 pl-5">
                  Allows up to 5 representative values per dimension to assist Gemini in writing precise SQL.
                </p>
              </div>

              <div className="flex justify-end space-x-2 pt-2 border-t">
                <button
                  type="button"
                  onClick={() => setUploadModalOpen(false)}
                  className="px-4 py-2 border rounded-lg text-slate-600 hover:bg-slate-50 font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={uploading}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium flex items-center space-x-1"
                >
                  {uploading ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      <span>Ingesting & Profiling...</span>
                    </>
                  ) : (
                    <span>Upload & Ingest</span>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Table Preview Drawer / Modal */}
      {previewOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
          <div className="bg-white rounded-2xl max-w-5xl w-full p-6 shadow-2xl space-y-4 max-h-[85vh] flex flex-col">
            <div className="flex items-center justify-between border-b pb-3">
              <div>
                <h3 className="text-base font-bold text-slate-900">
                  Data Preview: <span className="font-mono text-blue-600">{previewData?.table_name}</span>
                </h3>
                <p className="text-xs text-slate-500">
                  Showing first {previewData?.preview_rows_count} of {previewData?.total_rows.toLocaleString()} total rows via read-only engine.
                </p>
              </div>
              <button
                onClick={() => setPreviewOpen(false)}
                className="text-slate-400 hover:text-slate-600"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {previewLoading ? (
              <div className="py-12 text-center text-slate-400">
                <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-blue-500" />
                <p className="text-xs">Fetching preview rows...</p>
              </div>
            ) : previewData && previewData.rows.length > 0 ? (
              <div className="overflow-auto border rounded-lg flex-1">
                <table className="w-full text-left text-xs border-collapse font-mono">
                  <thead className="sticky top-0 bg-slate-100 border-b">
                    <tr>
                      {previewData.columns.map((col) => (
                        <th key={col} className="py-2 px-3 font-semibold text-slate-700 whitespace-nowrap">
                          {col}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {previewData.rows.map((row, idx) => (
                      <tr key={idx} className="hover:bg-slate-50">
                        {previewData.columns.map((col) => (
                          <td key={col} className="py-2 px-3 text-slate-600 whitespace-nowrap max-w-[200px] truncate">
                            {row[col] !== null ? String(row[col]) : <span className="text-slate-300 italic">null</span>}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="py-8 text-center text-slate-400 text-xs">No preview rows available.</div>
            )}

            <div className="flex justify-end pt-2 border-t">
              <button
                onClick={() => setPreviewOpen(false)}
                className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-semibold"
              >
                Close Preview
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default DatasetsPage;
