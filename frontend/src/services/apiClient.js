/**
 * Thin HTTP client around the AgriPredict API.
 *
 * Responsibilities kept deliberately narrow: build URLs, attach the bearer
 * token, normalise errors, and refresh an expired access token exactly once per
 * request. Screens never use `fetch` directly, so timeout and error-shape
 * handling cannot drift between features.
 */

import {API_BASE_URL, API_TIMEOUT_MS, API_DEBUG} from '../config';

export class ApiError extends Error {
  constructor(message, {status = 0, code = 'network_error', details = null} = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
  }

  /** True when retrying later could reasonably succeed. */
  get isRetryable() {
    return this.status === 0 || this.status >= 500 || this.status === 429;
  }

  get isAuthError() {
    return this.status === 401;
  }
}

let tokenProvider = () => null;
let refreshHandler = () => null;
let unauthorizedHandler = () => {};

/** Wire the client to whichever auth store is active (see AuthContext). */
export function configureApi({getToken, onRefresh, onUnauthorized}) {
  if (getToken) {
    tokenProvider = getToken;
  }
  if (onRefresh) {
    refreshHandler = onRefresh;
  }
  if (onUnauthorized) {
    unauthorizedHandler = onUnauthorized;
  }
}

export function resetApiConfiguration() {
  tokenProvider = () => null;
  refreshHandler = () => null;
  unauthorizedHandler = () => {};
}

function buildUrl(path, query) {
  const base = API_BASE_URL.replace(/\/$/, '');
  const suffix = path.startsWith('/') ? path : `/${path}`;
  const url = `${base}${suffix}`;
  if (!query) {
    return url;
  }
  const params = Object.entries(query)
    .filter(([, value]) => value !== undefined && value !== null && value !== '')
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`)
    .join('&');
  return params ? `${url}?${params}` : url;
}

async function parseBody(response) {
  const text = await response.text();
  if (!text) {
    return null;
  }
  try {
    return JSON.parse(text);
  } catch {
    return {raw: text};
  }
}

function toApiError(response, body) {
  const envelope = body && body.error ? body.error : {};
  return new ApiError(
    envelope.message || `Request failed with status ${response.status}`,
    {
      status: response.status,
      code: envelope.code || `http_${response.status}`,
      details: envelope.details || null,
    },
  );
}

async function rawRequest(method, path, {body, query, token, signal} = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), API_TIMEOUT_MS);
  // Respect a caller-supplied abort signal (screens unmount, for example).
  if (signal) {
    signal.addEventListener('abort', () => controller.abort());
  }

  const headers = {'Content-Type': 'application/json', Accept: 'application/json'};
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  if (API_DEBUG) {
    console.log(`[api] ${method} ${path}`);
  }

  try {
    const response = await fetch(buildUrl(path, query), {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
    const parsed = await parseBody(response);
    if (!response.ok) {
      throw toApiError(response, parsed);
    }
    return parsed;
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    if (error.name === 'AbortError') {
      throw new ApiError(
        'The request took too long. Please check your connection and try again.',
        {code: 'timeout'},
      );
    }
    throw new ApiError(
      'Could not reach the server. Check your internet connection.',
      {code: 'offline'},
    );
  } finally {
    clearTimeout(timeout);
  }
}

/**
 * Perform an authenticated request, refreshing the access token once if it has
 * expired. Concurrency is handled by the refresh handler in AuthContext, which
 * shares a single in-flight refresh across callers.
 */
async function request(method, path, options = {}) {
  const {skipAuth = false} = options;
  const token = skipAuth ? null : tokenProvider();

  try {
    return await rawRequest(method, path, {...options, token: token || undefined});
  } catch (error) {
    if (skipAuth || !(error instanceof ApiError) || !error.isAuthError) {
      throw error;
    }
    const refreshed = await refreshHandler();
    if (!refreshed) {
      unauthorizedHandler();
      throw new ApiError('Your session has expired. Please sign in again.', {
        status: 401,
        code: 'session_expired',
      });
    }
    return rawRequest(method, path, {...options, token: refreshed});
  }
}

export const api = {
  get: (path, options) => request('GET', path, options),
  post: (path, body, options) => request('POST', path, {...options, body}),
  patch: (path, body, options) => request('PATCH', path, {...options, body}),
  delete: (path, options) => request('DELETE', path, options),
  /** Unauthenticated request (login, register, public reference data). */
  publicGet: (path, options) => request('GET', path, {...options, skipAuth: true}),
  publicPost: (path, body, options) =>
    request('POST', path, {...options, body, skipAuth: true}),
};

export default api;
