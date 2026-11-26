import React from 'react';
import {StyleSheet, View} from 'react-native';

import {AppText, Button, Screen} from '../../components/ui';
import {useTheme} from '../../context/ThemeContext';
import {useTranslation} from '../../context/LocalizationContext';

export default function WelcomeScreen({navigation}) {
  const {theme} = useTheme();
  const {t} = useTranslation();

  return (
    <Screen>
      <View style={styles.body}>
        <View
          style={[
            styles.crest,
            {backgroundColor: theme.colors.surfaceAlt, borderColor: theme.colors.border},
          ]}>
          <AppText variant="h1" color={theme.colors.primary}>
            AP
          </AppText>
        </View>

        <AppText variant="h1" style={styles.title}>
          {t('auth.welcomeTitle')}
        </AppText>
        <AppText variant="body" color={theme.colors.textMuted} style={styles.subtitle}>
          {t('auth.welcomeSubtitle')}
        </AppText>
      </View>

      <View style={styles.actions}>
        <Button
          testID="welcome-login"
          title={t('auth.login')}
          onPress={() => navigation.navigate('Login')}
        />
        <Button
          testID="welcome-register"
          title={t('auth.register')}
          variant="secondary"
          onPress={() => navigation.navigate('Register')}
          style={styles.secondary}
        />
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  body: {flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 28},
  crest: {
    width: 84,
    height: 84,
    borderRadius: 42,
    borderWidth: StyleSheet.hairlineWidth,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 22,
  },
  title: {textAlign: 'center'},
  subtitle: {textAlign: 'center', marginTop: 10, maxWidth: 320},
  actions: {padding: 24, paddingBottom: 40},
  secondary: {marginTop: 12},
});
