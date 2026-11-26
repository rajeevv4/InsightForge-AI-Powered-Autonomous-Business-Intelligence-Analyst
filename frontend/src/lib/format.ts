/*
 * The one place numbers are formatted for display.
 *   formatMoney    -> "R$ 15,419,773.75", "₹ 36,62,817.30" (Indian lakh/crore grouping), "$ 1,234.50", or plain when no currency
 *   formatNumber   -> "96,478", "4.02" (averages always 2 decimals)
 *   formatCompact  -> "R$ 15.4M", "₹ 36.6L", "1.2K"
 *   formatPercent  -> "12.3%"
 * Values are never changed, only displayed: the Olist demo keeps its exact R$ figures.
 */

export type CurrencyCode = '' | '₹' | '$' | '€' | '£' | 'R$';
export const CURRENCY_OPTIONS: { code: CurrencyCode; label: string }[] = [
  { code: '', label: 'None' },
  { code: '₹', label: '₹ Rupee' },
  { code: '$', label: '$ Dollar' },
  { code: '€', label: '€ Euro' },
  { code: '£', label: '£ Pound' },
  { code: 'R$', label: 'R$ Real' },
];

const localeFor = (currency: CurrencyCode | null | undefined) => (currency === '₹' ? 'en-IN' : 'en-US');

const isBad = (v: unknown): boolean => v === null || v === undefined || (typeof v === 'number' && Number.isNaN(v));

export const formatNumber = (
  value: number | null | undefined,
  opts: { decimals?: number; avg?: boolean; locale?: string } = {}
): string => {
  if (isBad(value)) return '—';
  const v = value as number;
  const whole = Number.isInteger(v);
  const min = opts.decimals ?? (opts.avg ? 2 : 0);
  const max = opts.decimals ?? (opts.avg ? 2 : whole ? 0 : 2);
  return new Intl.NumberFormat(opts.locale || 'en-US', { minimumFractionDigits: min, maximumFractionDigits: max }).format(v);
};

export const formatMoney = (
  value: number | null | undefined,
  currency: CurrencyCode | null | undefined,
  opts: { decimals?: number } = {}
): string => {
  if (isBad(value)) return '—';
  const v = value as number;
  if (!currency) return formatNumber(v, { decimals: opts.decimals });
  const decimals = opts.decimals ?? 2;
  const body = new Intl.NumberFormat(localeFor(currency), { minimumFractionDigits: decimals, maximumFractionDigits: decimals }).format(Math.abs(v));
  return `${v < 0 ? '-' : ''}${currency} ${body}`;
};

export const formatCompact = (value: number | null | undefined, currency?: CurrencyCode | null): string => {
  if (isBad(value)) return '—';
  const v = value as number;
  const body = new Intl.NumberFormat(localeFor(currency), { notation: 'compact', maximumFractionDigits: 1 }).format(Math.abs(v));
  // non-breaking space: chart labels (SVG text) must never wrap "R$" onto its own line
  return `${v < 0 ? '-' : ''}${currency ? `${currency}\u00A0` : ''}${body}`;
};

export const formatPercent = (value: number | null | undefined, decimals = 1): string =>
  isBad(value) ? '—' : `${(value as number).toFixed(decimals)}%`;

export const formatSignedMoney = (value: number, currency: CurrencyCode | null | undefined, opts: { decimals?: number } = {}): string =>
  `${value >= 0 ? '+' : '-'}${formatMoney(Math.abs(value), currency, opts)}`;

/** Parse a server-formatted display string ("26,859.90", "-8,941") back to a number; null when it is not numeric. */
export const parseDisplayNumber = (s: string | null | undefined): number | null => {
  if (!s) return null;
  const cleaned = s.replace(/[^0-9.\-]/g, '');
  if (!cleaned || cleaned === '-' || cleaned === '.') return null;
  const n = Number(cleaned);
  return Number.isFinite(n) ? n : null;
};

/*
 * Which uploaded-dataset measures are money? (The backend does not know a currency; the user picks one.)
 * A measure is money when its name has a money word and no count / percent / rating word.
 */
const MONEY_WORDS = ['amount', 'price', 'revenue', 'sales', 'sale', 'cost', 'payment', 'spend', 'profit', 'income', 'fee', 'fees',
  'gmv', 'salary', 'balance', 'charge', 'charges', 'freight', 'tax', 'mrp', 'fare'];
const NOT_MONEY_WORDS = ['percent', 'pct', 'rate', 'ratio', 'count', 'qty', 'quantity', 'days', 'day', 'rating', 'score', 'rows',
  'units', 'number', 'id', 'age', 'year', 'month', 'hours', 'minutes', 'weight', 'distance', 'orders', 'items'];

export const isMoneyMeasure = (...names: (string | null | undefined)[]): boolean => {
  const tokens = names.filter(Boolean).join(' ').toLowerCase().split(/[^a-z0-9]+/).filter(Boolean);
  if (tokens.some((t) => NOT_MONEY_WORDS.includes(t))) return false;
  return tokens.some((t) => MONEY_WORDS.includes(t));
};

/** "order_items" -> "Order Items" (original names stay available in titles / tooltips). */
export const readableName = (safe: string): string =>
  safe.replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim().replace(/\b\w/g, (c) => c.toUpperCase());

/** Truncate for chart ticks; the full text goes in a <title> tooltip. */
export const truncateLabel = (s: string, max = 16): string => (s.length > max ? `${s.slice(0, max - 1)}…` : s);

/*
 * Server sentences for uploaded datasets carry no currency (the backend does not know it). When the user picked one,
 * add it to the amounts these fixed templates mark as money, re-grouped for the chosen locale:
 *   driver:  "City Delhi contributed +24,301 (118% of the spike)."  -> "... contributed +₹ 24,301 (...)"
 *   worth:   "..., worth +19,039."                                    -> "..., worth +₹ 19,039."
 */
const reformatAmount = (sign: string, num: string, currency: CurrencyCode): string => {
  const n = parseDisplayNumber(num);
  if (n === null) return `${sign}${num}`;
  const decimals = num.includes('.') ? 2 : 0;
  return `${sign}${formatMoney(n, currency, { decimals })}`;
};

export const currencyizeSentence = (s: string, currency: CurrencyCode | null | undefined): string => {
  if (!currency || !s) return s;
  return s
    .replace(/(contributed |moved the other way: |worth )([+-]?)(\d[\d,]*(?:\.\d+)?)/g, (_m, lead, sign, num) => `${lead}${reformatAmount(sign, num, currency)}`);
};
