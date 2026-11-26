import React, {useState} from 'react';
import {KeyboardAvoidingView, Platform, ScrollView, StyleSheet, View} from 'react-native';

import {AppText, Button, Input, Screen} from '../../components/ui';
import {useAuth} from '../../context/AuthContext';
import {useTheme} from '../../context/ThemeContext';
import {useTranslation} from '../../context/LocalizationContext';
import {mapApiError} from '../../utils/errors';
import {required, validEmail} from '../../utils/validation';

export default function LoginScreen({navigation}) {
  const {theme} = useTheme();
  const {t} = useTranslation();
  const {login} = useAuth();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState({});
  const [formError, setFormError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit() {
    const nextErrors = {
      email: validEmail(email),
      password: required(password),
    };
    const cleaned = Object.fromEntries(
      Object.entries(nextErrors).filter(([, value]) => Boolean(value)),
    );
    setErrors(cleaned);
    setFormError(null);
    if (Object.keys(cleaned).length > 0) {
      return;
    }

    setSubmitting(true);
    try {
      await login({email: email.trim(), password});
      // Navigation switches automatically once auth status changes.
    } catch (error) {
      setFormError(mapApiError(error).messageKey);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Screen>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          <AppText variant="h1">{t('auth.loginTitle')}</AppText>

          {formError ? (
            <View
              style={[
                styles.banner,
                {backgroundColor: theme.colors.surfaceAlt, borderColor: theme.colors.danger},
              ]}>
              <AppText variant="caption" color={theme.colors.danger} testID="login-error">
                {t(formError)}
              </AppText>
            </View>
          ) : null}

          <Input
            testID="login-email"
            label={t('auth.email')}
            value={email}
            onChangeText={setEmail}
            placeholder={t('auth.emailPlaceholder')}
            keyboardType="email-address"
            autoCapitalize="none"
            autoCorrect={false}
            autoComplete="email"
            textContentType="emailAddress"
            error={errors.email ? t(errors.email) : undefined}
          />

          <Input
            testID="login-password"
            label={t('auth.password')}
            value={password}
            onChangeText={setPassword}
            placeholder={t('auth.passwordPlaceholder')}
            secureTextEntry
            autoCapitalize="none"
            autoComplete="password"
            textContentType="password"
            error={errors.password ? t(errors.password) : undefined}
            onSubmitEditing={onSubmit}
            returnKeyType="go"
          />

          <Button
            testID="login-submit"
            title={t('auth.login')}
            onPress={onSubmit}
            loading={submitting}
          />

          <Button
            testID="login-go-register"
            title={t('auth.noAccount')}
            variant="ghost"
            onPress={() => navigation.navigate('Register')}
            style={styles.switch}
          />
        </ScrollView>
      </KeyboardAvoidingView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  flex: {flex: 1},
  content: {padding: 24, paddingTop: 40},
  banner: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 8,
    padding: 12,
    marginTop: 16,
    marginBottom: 4,
  },
  switch: {marginTop: 10},
});
