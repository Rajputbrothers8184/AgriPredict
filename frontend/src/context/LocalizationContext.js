/**
 * Language provider: persistence, RTL layout direction, and `t()`.
 */

import React, {createContext, useCallback, useContext, useEffect, useMemo, useState} from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import {I18nManager} from 'react-native';

import {DEFAULT_LANGUAGE, STORAGE_KEYS} from '../config';
import {CATALOGUES, LANGUAGES, isRtl, translate} from '../localization';

const LocalizationContext = createContext(null);

export function LocalizationProvider({children, initialLanguage}) {
  const [language, setLanguageState] = useState(initialLanguage || DEFAULT_LANGUAGE);
  const [loaded, setLoaded] = useState(Boolean(initialLanguage));

  useEffect(() => {
    let active = true;
    AsyncStorage.getItem(STORAGE_KEYS.language)
      .then(stored => {
        if (active && stored && CATALOGUES[stored]) {
          setLanguageState(stored);
        }
      })
      .catch(() => {})
      .finally(() => active && setLoaded(true));
    return () => {
      active = false;
    };
  }, []);

  const setLanguage = useCallback(async next => {
    if (!CATALOGUES[next]) {
      return;
    }
    setLanguageState(next);
    try {
      await AsyncStorage.setItem(STORAGE_KEYS.language, next);
    } catch {
      // Non-fatal: the choice still applies for this session.
    }
    // RN cannot flip layout direction at runtime without a reload; record the
    // preference so the next launch renders correctly, and note it for the user.
    const shouldBeRtl = isRtl(next);
    if (I18nManager.isRTL !== shouldBeRtl) {
      I18nManager.allowRTL(shouldBeRtl);
      I18nManager.forceRTL(shouldBeRtl);
    }
  }, []);

  const t = useCallback((key, params) => translate(language, key, params), [language]);

  const value = useMemo(
    () => ({
      language,
      isRtl: isRtl(language),
      languages: LANGUAGES,
      setLanguage,
      loaded,
      t,
    }),
    [language, setLanguage, loaded, t],
  );

  return (
    <LocalizationContext.Provider value={value}>{children}</LocalizationContext.Provider>
  );
}

export function useTranslation() {
  const context = useContext(LocalizationContext);
  if (!context) {
    throw new Error('useTranslation must be used inside a LocalizationProvider');
  }
  return context;
}

export default LocalizationContext;
