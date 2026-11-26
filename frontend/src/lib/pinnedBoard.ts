import { PinnedCardSpec } from '../types/api';

const STORAGE_KEY = 'insightforge_pinned_board_v1';
const MAX_PINS = 20;

export function getPinnedCards(): PinnedCardSpec[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    // Never load or trust any accidentally stored rows
    return parsed.map((item) => ({
      id: String(item.id || ''),
      question: String(item.question || ''),
      route: item.route === 'intent' ? 'intent' : 'text_to_sql',
      intent: item.intent || null,
      sql: item.sql || null,
      dataset_id: String(item.dataset_id || 'olist_demo'),
      dataset_name: String(item.dataset_name || 'Olist Demo'),
      chart_spec:
        item.chart_spec === 'line' || item.chart_spec === 'pie' || item.chart_spec === 'table'
          ? item.chart_spec
          : 'bar',
      pinned_at: String(item.pinned_at || new Date().toISOString()),
    }));
  } catch {
    return [];
  }
}

export function addPinnedCard(spec: Omit<PinnedCardSpec, 'id' | 'pinned_at'>): PinnedCardSpec[] {
  const current = getPinnedCards();
  const deduped = current.filter(
    (c) => !(c.dataset_id === spec.dataset_id && c.question.toLowerCase() === spec.question.trim().toLowerCase())
  );
  const newCard: PinnedCardSpec = {
    id: `pin_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    question: spec.question.trim(),
    route: spec.route,
    intent: spec.intent || null,
    sql: spec.sql || null,
    dataset_id: spec.dataset_id,
    dataset_name: spec.dataset_name,
    chart_spec: spec.chart_spec,
    pinned_at: new Date().toISOString(),
  };
  const next = [newCard, ...deduped].slice(0, MAX_PINS);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  return next;
}

export function removePinnedCard(id: string): PinnedCardSpec[] {
  const next = getPinnedCards().filter((c) => c.id !== id);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  return next;
}

export function isQuestionPinned(question: string, datasetId: string): boolean {
  const q = question.trim().toLowerCase();
  return getPinnedCards().some((c) => c.dataset_id === datasetId && c.question.toLowerCase() === q);
}
