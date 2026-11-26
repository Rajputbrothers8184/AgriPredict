/**
 * Session storage and in-flight refresh coordination.
 *
 * Kept outside React so that (a) it can be unit-tested without rendering, and
 * (b) `apiClient` can call `refreshSession()` synchronously during a retry.
 *
 * Refresh concurrency: if three screens fire requests at once and the access
 * token has expired, all three receive 401 and would each call /auth/refresh.
 * Because refresh tokens rotate, only the first would succeed and the other two
 * would be logged out. `refreshPromise` collapses them into one request.
 */

import AsyncStorage from '@react-native-async-storage/async-storage';

import {STORAGE_KEYS} from '../config';
import {authApi} from './api';

let tokens = {accessToken: null, refreshToken: null};
let currentUser = null;
let refreshPromise = null;
let onSessionLost = () => {};

export function setSessionLostHandler(handler) {
  onSessionLost = handler || (() => {});
}

export function getAccessToken() {
  return tokens.accessToken;
}

export function getRefreshToken() {
  return tokens.refreshToken;
}

export function getCurrentUser() {
  return currentUser;
}

export function setUser(user) {
  currentUser = user;
}

export function setTokens(next) {
  tokens = {
    accessToken: next.accessToken || null,
    refreshToken: next.refreshToken || null,
  };
}

export async function persistSession({accessToken, refreshToken, user}) {
  setTokens({accessToken, refreshToken});
  currentUser = user || currentUser;
  const pairs = [];
  if (accessToken) {
    pairs.push([STORAGE_KEYS.accessToken, accessToken]);
  }
  if (refreshToken) {
    pairs.push([STORAGE_KEYS.refreshToken, refreshToken]);
  }
  if (user) {
    pairs.push([STORAGE_KEYS.user, JSON.stringify(user)]);
  }
  if (pairs.length) {
    try {
      await AsyncStorage.multiSet(pairs);
    } catch {
      // Storage failure must not sign the user out for this session.
    }
  }
}

export async function restoreSession() {
  try {
    const entries = await AsyncStorage.multiGet([
      STORAGE_KEYS.accessToken,
      STORAGE_KEYS.refreshToken,
      STORAGE_KEYS.user,
    ]);
    const map = Object.fromEntries(entries);
    setTokens({
      accessToken: map[STORAGE_KEYS.accessToken],
      refreshToken: map[STORAGE_KEYS.refreshToken],
    });
    currentUser = map[STORAGE_KEYS.user] ? JSON.parse(map[STORAGE_KEYS.user]) : null;
    return {accessToken: tokens.accessToken, refreshToken: tokens.refreshToken, user: currentUser};
  } catch {
    setTokens({accessToken: null, refreshToken: null});
    currentUser = null;
    return {accessToken: null, refreshToken: null, user: null};
  }
}

export async function clearSession() {
  setTokens({accessToken: null, refreshToken: null});
  currentUser = null;
  refreshPromise = null;
  try {
    await AsyncStorage.multiRemove([
      STORAGE_KEYS.accessToken,
      STORAGE_KEYS.refreshToken,
      STORAGE_KEYS.user,
    ]);
  } catch {
    // Ignore: the in-memory session is already cleared.
  }
}

/**
 * Exchange the refresh token for a new pair. Returns the new access token, or
 * null when the session is genuinely over.
 */
export async function refreshSession() {
  if (refreshPromise) {
    return refreshPromise;
  }
  const refreshToken = tokens.refreshToken;
  if (!refreshToken) {
    return null;
  }

  refreshPromise = (async () => {
    try {
      const pair = await authApi.refresh(refreshToken);
      await persistSession({
        accessToken: pair.access_token,
        refreshToken: pair.refresh_token,
        user: currentUser,
      });
      return pair.access_token;
    } catch {
      await clearSession();
      onSessionLost();
      return null;
    } finally {
      refreshPromise = null;
    }
  })();

  return refreshPromise;
}

/** Test helper. */
export function __resetSession() {
  tokens = {accessToken: null, refreshToken: null};
  currentUser = null;
  refreshPromise = null;
  onSessionLost = () => {};
}
