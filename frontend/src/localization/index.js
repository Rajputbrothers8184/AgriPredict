/**
 * Translation lookup with placeholder interpolation and RTL support.
 *
 * Deliberately dependency-free: `i18n-js` and `react-i18next` both work, but the
 * requirement is a two-locale catalogue with placeholders, and a 60-line
 * implementation is easier to test and audit than a framework.
 */

import en from './en';
import ur from './ur';

export const LANGUAGES = {
  en: {label: 'English', nativeLabel: 'English', rtl: false},
  ur: {label: 'Urdu', nativeLabel: 'اردو', rtl: true},
};

export const CATALOGUES = {en, ur};
export const DEFAULT_LANGUAGE = 'en';

/** Resolve a dotted key ("crops.title") in a catalogue. */
export function lookup(catalogue, key) {
  return key.split('.').reduce((node, part) => (node && node[part] !== undefined ? node[part] : undefined), catalogue);
}

/**
 * Interpolate {placeholders}. Unknown placeholders are left intact so a missing
 * value is visible in development instead of silently rendering "undefined".
 */
export function interpolate(template, params = {}) {
  if (typeof template !== 'string') {
    return template;
  }
  return template.replace(/\{(\w+)\}/g, (match, name) =>
    params[name] !== undefined && params[name] !== null ? String(params[name]) : match,
  );
}

/**
 * Translate `key` in `language`, falling back to English and then to the key
 * itself. A visible key is a bug report; `undefined` on screen is not.
 */
export function translate(language, key, params) {
  const catalogue = CATALOGUES[language] || CATALOGUES[DEFAULT_LANGUAGE];
  let value = lookup(catalogue, key);
  if (value === undefined) {
    value = lookup(CATALOGUES[DEFAULT_LANGUAGE], key);
  }
  if (value === undefined) {
    if (__DEV__) {
      console.warn(`[i18n] missing translation: ${key}`);
    }
    return key;
  }
  return interpolate(value, params);
}

export function isRtl(language) {
  return Boolean(LANGUAGES[language] && LANGUAGES[language].rtl);
}

/** Flatten a catalogue to dotted keys — used by the parity test. */
export function flattenKeys(catalogue, prefix = '') {
  return Object.entries(catalogue).flatMap(([key, value]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    if (value && typeof value === 'object') {
      return flattenKeys(value, path);
    }
    return [path];
  });
}

/** Check that every key in `reference` exists in `candidate`. */
export function missingKeys(reference, candidate) {
  const present = new Set(flattenKeys(candidate));
  return flattenKeys(reference).filter(key => !present.has(key));
}

/** Placeholders used in a template, e.g. {name} -> ["name"]. */
export function placeholdersIn(template) {
  if (typeof template !== 'string') {
    return [];
  }
  return [...template.matchAll(/\{(\w+)\}/g)].map(match => match[1]).sort();
}

export default {translate, interpolate, isRtl, LANGUAGES, CATALOGUES};
