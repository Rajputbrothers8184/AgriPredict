/**
 * Endpoint wrappers: one function per backend route.
 *
 * Field names mirror the FastAPI schemas in `backend/app/schemas/__init__.py`
 * exactly (`amount_pkr`, `unit_price_pkr`, `total_area_acres`, …). Money and
 * quantity values arrive as *strings* because the API serialises Decimal; every
 * screen passes them through `toNumber` before doing arithmetic.
 */

import {API_ORIGIN} from '../config';
import api from './apiClient';

// --- Auth -----------------------------------------------------------------
export const authApi = {
  register: ({email, password, fullName, phone, preferredLanguage}) =>
    api.publicPost('/auth/register', {
      email,
      password,
      full_name: fullName,
      phone: phone || null,
      preferred_language: preferredLanguage || 'en',
    }),
  login: ({email, password}) => api.publicPost('/auth/login', {email, password}),
  refresh: refreshToken => api.publicPost('/auth/refresh', {refresh_token: refreshToken}),
  logout: refreshToken => api.post('/auth/logout', {refresh_token: refreshToken}),
  logoutAll: () => api.post('/auth/logout-all'),
  me: () => api.get('/auth/me'),
  updateProfile: changes => api.patch('/auth/me', changes),
  changePassword: ({currentPassword, newPassword}) =>
    api.post('/auth/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    }),
};

// --- Farms ----------------------------------------------------------------
export const farmApi = {
  list: () => api.get('/farms'),
  create: farm => api.post('/farms', farm),
  get: id => api.get(`/farms/${id}`),
  update: (id, changes) => api.patch(`/farms/${id}`, changes),
  remove: id => api.delete(`/farms/${id}`),
};

// --- Reference data -------------------------------------------------------
export const catalogueApi = {
  commodities: () => api.get('/markets/commodities'),
  markets: () => api.get('/markets/list'),
};

/** Language-aware commodity label, falling back to the slug. */
export function commodityName(commodity, language = 'en') {
  if (!commodity) {
    return '';
  }
  if (language === 'ur' && commodity.name_ur) {
    return commodity.name_ur;
  }
  return commodity.name_en || commodity.name || commodity.slug || '';
}

// --- Crop cycles ----------------------------------------------------------
export const cropApi = {
  list: (filters = {}) => api.get('/crop-cycles', {query: filters}),
  create: cycle => api.post('/crop-cycles', cycle),
  /** Returns CropCycleDetail, including the server-computed `finance` block. */
  get: id => api.get(`/crop-cycles/${id}`),
  update: (id, changes) => api.patch(`/crop-cycles/${id}`, changes),
  remove: id => api.delete(`/crop-cycles/${id}`),

  expenses: (id, category) => api.get(`/crop-cycles/${id}/expenses`, {query: {category}}),
  addExpense: (id, expense) => api.post(`/crop-cycles/${id}/expenses`, expense),
  updateExpense: (id, expenseId, changes) =>
    api.patch(`/crop-cycles/${id}/expenses/${expenseId}`, changes),
  removeExpense: (id, expenseId) =>
    api.delete(`/crop-cycles/${id}/expenses/${expenseId}`),

  sales: id => api.get(`/crop-cycles/${id}/sales`),
  addSale: (id, sale) => api.post(`/crop-cycles/${id}/sales`, sale),
  updateSale: (id, saleId, changes) =>
    api.patch(`/crop-cycles/${id}/sales/${saleId}`, changes),
  removeSale: (id, saleId) => api.delete(`/crop-cycles/${id}/sales/${saleId}`),
};

// --- Markets, prices, forecasts ------------------------------------------
export const marketApi = {
  /** -> PriceHistory {commodity, market, unit, points[{price_date, avg_price_pkr, …}], count} */
  history: (commoditySlug, marketSlug, days = 90) =>
    api.get(`/markets/history/${commoditySlug}/${marketSlug}`, {query: {days}}),
  /** -> MarketComparison {commodity, unit, rows[{market, latest_price_pkr, …}], best_market_slug} */
  compare: (commoditySlug, {days = 30, district} = {}) =>
    api.get(`/markets/compare/${commoditySlug}`, {query: {days, district}}),
};

export const forecastApi = {
  /** -> ForecastRead {points[{target_date, predicted_price_pkr, lower_bound_pkr, …}], …} */
  get: (commoditySlug, marketSlug, horizon = 7, {refresh = false} = {}) =>
    api.get(`/forecasts/${commoditySlug}/${marketSlug}`, {
      query: {horizon, refresh},
    }),
  latest: (commoditySlug, marketSlug, horizon = 7) =>
    api.get(`/forecasts/latest/${commoditySlug}/${marketSlug}`, {query: {horizon}}),
};

// --- Weather / buyers -----------------------------------------------------
export const weatherApi = {
  /** -> WeatherBundle {current, forecast[], provider, is_live} */
  forFarm: (farmId, {refresh = false} = {}) =>
    api.get(`/weather/${farmId}`, {query: {refresh}}),
  current: ({latitude, longitude}) =>
    api.get('/weather/current', {query: {latitude, longitude}}),
};

export const buyerApi = {
  /** -> BuyerSearchResponse {results[], count, radius_m, source, note} */
  search: ({latitude, longitude, district, radiusM, limit, cacheOnly} = {}) =>
    api.get('/buyers', {
      query: {
        latitude,
        longitude,
        district,
        radius_m: radiusM,
        limit,
        cache_only: cacheOnly,
      },
    }),
  nearFarm: (farmId, {radiusM, limit} = {}) =>
    api.get(`/buyers/farm/${farmId}`, {query: {radius_m: radiusM, limit}}),
  /** -> BuyerRead[] (a bare list, unlike /buyers which wraps in `results`) */
  saved: (limit = 50) => api.get('/buyers/saved', {query: {limit}}),
};

// --- Finance / reports ----------------------------------------------------
export const financeApi = {
  /** -> FinanceOverview {lifetime_revenue_pkr, …, seasons[], expense_breakdown[]} */
  summary: () => api.get('/finance/summary'),
  /** -> SeasonSummary[] {season, year, cycles, revenue_pkr, cost_pkr, profit_pkr, margin_pct} */
  seasons: () => api.get('/finance/seasons'),
  /** -> ExpenseBreakdownRow[] {category, total_pkr, share_pct} */
  expenses: (filters = {}) => api.get('/finance/expenses', {query: filters}),
};

export const reportApi = {
  /** -> ReportRead {id, report_type, file_format, filename, download_url, …} */
  create: ({reportType, fileFormat, cropCycleId}) =>
    api.post('/reports', {
      report_type: reportType,
      file_format: fileFormat,
      crop_cycle_id: cropCycleId || null,
    }),
  list: () => api.get('/reports'),
};

/**
 * The server returns a relative `download_url` carrying a short-lived signed
 * token, precisely so a browser/download manager without an Authorization
 * header can fetch it. Join it to the API origin; never re-attach the token.
 */
export function absoluteDownloadUrl(report) {
  const url = report && report.download_url;
  if (!url) {
    return null;
  }
  return url.startsWith('http') ? url : `${API_ORIGIN}${url}`;
}
