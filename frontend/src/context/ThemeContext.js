/**
 * Theme provider: light, dark, or follow the system, persisted locally.
 *
 * `useColorScheme` reports the OS preference; when the user picks "system" the
 * app re-renders if the OS theme changes mid-session.
 */

import React, {createContext, useCallback, useContext, useEffect, useMemo, useState} from 'react';
import {useColorScheme} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';

import {DEFAULT_THEME, STORAGE_KEYS} from '../config';
import {palettes} from '../theme/palette';

const ThemeContext = createContext(null);

export function ThemeProvider({children, initialTheme}) {
  const systemScheme = useColorScheme();
  const [preference, setPreference] = useState(initialTheme || DEFAULT_THEME);
  const [loaded, setLoaded] = useState(Boolean(initialTheme));

  useEffect(() => {
    let active = true;
    AsyncStorage.getItem(STORAGE_KEYS.theme)
      .then(stored => {
        if (active && stored) {
          setPreference(stored);
        }
      })
      .catch(() => {})
      .finally(() => active && setLoaded(true));
    return () => {
      active = false;
    };
  }, []);

  const resolved = useMemo(() => {
    if (preference === 'system') {
      return systemScheme === 'dark' ? 'dark' : 'light';
    }
    return preference === 'dark' ? 'dark' : 'light';
  }, [preference, systemScheme]);

  const setTheme = useCallback(async next => {
    if (!['light', 'dark', 'system'].includes(next)) {
      return;
    }
    setPreference(next);
    try {
      await AsyncStorage.setItem(STORAGE_KEYS.theme, next);
    } catch {
      // Persistence is a convenience; the in-memory theme still applies.
    }
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme(resolved === 'dark' ? 'light' : 'dark');
  }, [resolved, setTheme]);

  const value = useMemo(
    () => ({
      preference,
      mode: resolved,
      theme: palettes[resolved],
      isDark: resolved === 'dark',
      loaded,
      setTheme,
      toggleTheme,
    }),
    [preference, resolved, loaded, setTheme, toggleTheme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used inside a ThemeProvider');
  }
  return context;
}

export default ThemeContext;
