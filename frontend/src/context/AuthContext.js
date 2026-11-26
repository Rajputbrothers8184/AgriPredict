/**
 * Authentication state for the whole app.
 *
 * The heavy lifting (storage, refresh rotation) lives in `services/session.js`;
 * this provider adds React state, navigation-relevant flags, and wires the API
 * client so a 401 anywhere triggers exactly one refresh.
 */

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import {configureApi} from '../services/apiClient';
import {authApi} from '../services/api';
import {
  clearSession,
  getAccessToken,
  getCurrentUser,
  persistSession,
  refreshSession,
  restoreSession,
  setSessionLostHandler,
  setUser,
} from '../services/session';

const AuthContext = createContext(null);

export function AuthProvider({children}) {
  const [user, setUserState] = useState(null);
  const [status, setStatus] = useState('restoring'); // restoring | anonymous | authenticated
  const sessionLostRef = useRef(false);

  const applySession = useCallback(async payload => {
    await persistSession({
      accessToken: payload.access_token,
      refreshToken: payload.refresh_token,
      user: payload.user,
    });
    setUserState(payload.user);
    setStatus('authenticated');
  }, []);

  const handleSessionLost = useCallback(async () => {
    sessionLostRef.current = true;
    await clearSession();
    setUserState(null);
    setStatus('anonymous');
  }, []);

  // Wire the API client once: it asks this module for the token, and asks it to
  // refresh rather than trying to manage tokens itself.
  useEffect(() => {
    setSessionLostHandler(handleSessionLost);
    configureApi({
      getToken: () => getAccessToken(),
      onRefresh: () => refreshSession(),
      onUnauthorized: () => handleSessionLost(),
    });
  }, [handleSessionLost]);

  // Restore a stored session on launch, then confirm it with the server.
  useEffect(() => {
    let active = true;
    (async () => {
      const restored = await restoreSession();
      if (!active) {
        return;
      }
      if (!restored.accessToken) {
        setStatus('anonymous');
        return;
      }
      setUserState(restored.user);
      try {
        const me = await authApi.me();
        if (!active) {
          return;
        }
        setUser(me);
        setUserState(me);
        setStatus('authenticated');
      } catch {
        // A failed /me with a valid-looking token means the session is dead
        // (rotated secret, deactivated account). Do not show a half-session.
        if (active) {
          await handleSessionLost();
        }
      }
    })();
    return () => {
      active = false;
    };
  }, [handleSessionLost]);

  const login = useCallback(
    async ({email, password}) => {
      const pair = await authApi.login({email, password});
      const me = await authApi.me();
      await applySession({...pair, user: me});
      return me;
    },
    [applySession],
  );

  const register = useCallback(
    async ({email, password, fullName, phone, preferredLanguage}) => {
      const pair = await authApi.register({
        email,
        password,
        fullName,
        phone,
        preferredLanguage,
      });
      const me = await authApi.me();
      await applySession({...pair, user: me});
      return me;
    },
    [applySession],
  );

  const logout = useCallback(async () => {
    const refreshToken = await import('../services/session').then(m => m.getRefreshToken());
    if (refreshToken) {
      try {
        await authApi.logout(refreshToken);
      } catch {
        // Server-side revocation is best effort; the local session is cleared
        // regardless, which is what the user asked for.
      }
    }
    await handleSessionLost();
  }, [handleSessionLost]);

  const updateProfile = useCallback(async changes => {
    const updated = await authApi.updateProfile(changes);
    setUser(updated);
    setUserState(updated);
    return updated;
  }, []);

  const changePassword = useCallback(async ({currentPassword, newPassword}) => {
    await authApi.changePassword({currentPassword, newPassword});
    // The backend bumps token_version, so every session is invalid.
    await handleSessionLost();
  }, [handleSessionLost]);

  const refreshUser = useCallback(async () => {
    const me = await authApi.me();
    setUser(me);
    setUserState(me);
    return me;
  }, []);

  const value = useMemo(
    () => ({
      user,
      status,
      isLoading: status === 'restoring',
      isAuthenticated: status === 'authenticated',
      sessionLost: sessionLostRef.current,
      login,
      register,
      logout,
      updateProfile,
      changePassword,
      refreshUser,
      currentUser: () => getCurrentUser(),
    }),
    [user, status, login, register, logout, updateProfile, changePassword, refreshUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used inside an AuthProvider');
  }
  return context;
}

export default AuthContext;
