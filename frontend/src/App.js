import React from 'react';
import {StatusBar} from 'react-native';
import {SafeAreaProvider} from 'react-native-safe-area-context';

import RootNavigator from './navigation/RootNavigator';
import {AuthProvider} from './context/AuthContext';
import {LocalizationProvider} from './context/LocalizationContext';
import {ThemeProvider, useTheme} from './context/ThemeContext';

function ThemedApp() {
  const {isDark, theme} = useTheme();
  return (
    <>
      <StatusBar
        barStyle={isDark ? 'light-content' : 'dark-content'}
        backgroundColor={theme.colors.surface}
      />
      <AuthProvider>
        <RootNavigator />
      </AuthProvider>
    </>
  );
}

export default function App() {
  return (
    <SafeAreaProvider>
      <ThemeProvider>
        <LocalizationProvider>
          <ThemedApp />
        </LocalizationProvider>
      </ThemeProvider>
    </SafeAreaProvider>
  );
}
