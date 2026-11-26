/**
 * Formatting helpers.
 *
 * All money in AgriPredict is in PKR and all prices are **per 40 kg maund**.
 * Formatting lives here (rather than inline) so the unit can never be dropped
 * from a label — a price shown without its unit is the most likely source of a
 * factor-of-40 misunderstanding.
 */

import {PRICE_UNIT} from '../config';

/**
 * Grouping is implemented by hand rather than with Intl.NumberFormat.
 *
 * Two concrete reasons:
 *  1. Only some ICU builds render ISO currency code "PKR"; others render
 *     "Rs", so the same build would label money differently on different
 *     devices.
 *  2. Hermes' Intl coverage on Android is partial by design, and a missing
 *     currency implementation would throw at the first price render.
 *
 * South Asian grouping (1,23,456) is *not* used: Pakistani mandi price lists,
 * bank statements and PBS tables all use the international 3-digit grouping,
 * and matching the sources the user compares against matters more than local
 * convention.
 */
function groupThousands(text) {
  const [whole, fraction] = text.split('.');
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  return fraction === undefined ? grouped : `${grouped}.${fraction}`;
}

function withThousands(value, decimals = 0) {
  const rounded = Number(value).toFixed(decimals);
  // Avoid "-0" / "-0.00", which reads as an error in a ledger.
  const normalised = Number(rounded) === 0 ? (0).toFixed(decimals) : rounded;
  return groupThousands(normalised.startsWith('-') ? normalised.slice(1) : normalised).replace(
    /^/,
    normalised.startsWith('-') ? '-' : '',
  );
}

/** Numeric coercion that tolerates the API's decimal strings. */
export function toNumber(value) {
  if (value === null || value === undefined || value === '') {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/** "PKR 3,900" — the common case for list rows. */
export function formatPrice(value) {
  const number = toNumber(value);
  if (number === null) {
    return '—';
  }
  return `PKR ${withThousands(number, 0)}`;
}

/** "PKR 3,900.50" — used where paisa matter (statements, exports). */
export function formatPriceExact(value) {
  const number = toNumber(value);
  if (number === null) {
    return '—';
  }
  return `PKR ${withThousands(number, 2)}`;
}

/** "3,900 PKR/40kg" — the explicit form, for chart axes and comparisons. */
export function formatPriceWithUnit(value) {
  const number = toNumber(value);
  if (number === null) {
    return '—';
  }
  return `PKR ${withThousands(number, 0)} ${PRICE_UNIT}`;
}

export function formatCompact(value) {
  const number = toNumber(value);
  if (number === null) {
    return '—';
  }
  if (Math.abs(number) >= 10000000) {
    return `${(number / 10000000).toFixed(1)} crore`;
  }
  if (Math.abs(number) >= 100000) {
    return `${(number / 100000).toFixed(1)} lakh`;
  }
  if (Math.abs(number) >= 1000) {
    return `${(number / 1000).toFixed(1)}k`;
  }
  return `${number}`;
}

export function formatPercent(value, digits = 1) {
  const number = toNumber(value);
  if (number === null) {
    return '—';
  }
  return `${number.toFixed(digits)}%`;
}

/** "12.50 acre" — quantities keep their unit for the same reason prices do. */
export function formatArea(value) {
  const number = toNumber(value);
  if (number === null) {
    return '—';
  }
  return `${number.toFixed(number % 1 === 0 ? 0 : 2)} acre`;
}

export function formatQuantityKg(value) {
  const number = toNumber(value);
  if (number === null) {
    return '—';
  }
  if (number >= 1000) {
    return `${(number / 1000).toFixed(2)} tonne`;
  }
  return `${number.toFixed(0)} kg`;
}

/** ISO date (YYYY-MM-DD) or timestamp -> "12 Nov 2026". */
export function formatDate(value, locale = 'en-GB') {
  if (!value) {
    return '—';
  }
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) {
    return '—';
  }
  return date.toLocaleDateString(locale, {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });
}

export function formatDateTime(value, locale = 'en-GB') {
  if (!value) {
    return '—';
  }
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) {
    return '—';
  }
  return date.toLocaleString(locale, {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/** Whole days between two dates, for "harvest in N days" style hints. */
export function daysUntil(target) {
  if (!target) {
    return null;
  }
  const date = target instanceof Date ? target : new Date(target);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  date.setHours(0, 0, 0, 0);
  return Math.round((date - today) / (1000 * 60 * 60 * 24));
}

/** Today as YYYY-MM-DD (the format every API date field uses). */
export function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

/** True for a finite, non-negative number (used by form validation). */
export function isPositiveNumber(value) {
  const number = toNumber(value);
  return number !== null && number > 0;
}
