/**
 * Runtime configuration.
 *
 * Values come from the environment at build time. `react-native-config` is not
 * a dependency, so `process.env.*` is populated by babel's inline transform in
 * the standard RN template; when a value is absent the fallbacks below apply.
 * That keeps a fresh clone runnable without an extra native module.
 */

const DEFAULT_API_BASE_URL = 'http://10.0.2.2:8000/api/v1';

const env = (typeof process !== 'undefined' && process.env) || {};

export const API_BASE_URL = env.API_BASE_URL || DEFAULT_API_BASE_URL;

/**
 * Scheme+host only (e.g. "http://10.0.2.2:8000").
 *
 * The API returns `download_url` as a server-relative path such as
 * "/api/v1/reports/3/download?token=…", which must be joined to this, not to
 * API_BASE_URL (that would duplicate the /api/v1 prefix).
 */
export const API_ORIGIN = API_BASE_URL.replace(/\/api\/v1\/?$/, '');
export const API_TIMEOUT_MS = Number(env.API_TIMEOUT_MS || 15000);
export const API_DEBUG = String(env.API_DEBUG || 'false') === 'true';
export const DEFAULT_LANGUAGE = env.DEFAULT_LANGUAGE === 'ur' ? 'ur' : 'en';
export const DEFAULT_THEME = ['light', 'dark', 'system'].includes(env.DEFAULT_THEME)
  ? env.DEFAULT_THEME
  : 'system';

/** Storage keys. Namespaced so a future migration is obvious. */
export const STORAGE_KEYS = {
  accessToken: '@agripredict/access_token',
  refreshToken: '@agripredict/refresh_token',
  user: '@agripredict/user',
  language: '@agripredict/language',
  theme: '@agripredict/theme',
  lastSync: '@agripredict/last_sync',
};

/** Price unit used across the UI. Must match the backend and the database. */
export const PRICE_UNIT = 'PKR/40kg';

export default {
  API_BASE_URL,
  API_ORIGIN,
  API_TIMEOUT_MS,
  API_DEBUG,
  DEFAULT_LANGUAGE,
  DEFAULT_THEME,
  STORAGE_KEYS,
  PRICE_UNIT,
};
