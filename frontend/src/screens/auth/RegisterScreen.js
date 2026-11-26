import React, {useState} from 'react';
import {KeyboardAvoidingView, Platform, ScrollView, StyleSheet, View} from 'react-native';

import {AppText, Button, Input, Screen} from '../../components/ui';
import {useAuth} from '../../context/AuthContext';
import {useTheme} from '../../context/ThemeContext';
import {useTranslation} from '../../context/LocalizationContext';
import {mapApiError} from '../../utils/errors';
import {passwordsMatch, required, validEmail, validPassword} from '../../utils/validation';

export default function RegisterScreen({navigation}) {
  const {theme} = useTheme();
  const {t, language} = useTranslation();
  const {register} = useAuth();

  const [form, setForm] = useState({
    fullName: '',
    email: '',
    phone: '',
    password: '',
    confirm: '',
  });
  const [errors, setErrors] = useState({});
  const [formError, setFormError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  function update(key, value) {
    setForm(previous => ({...previous, [key]: value}));
  }

  async function onSubmit() {
    const nextErrors = {
      fullName: required(form.fullName),
      email: validEmail(form.email),
      password: validPassword(form.password),
      confirm: passwordsMatch(form.password, form.confirm),
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
      await register({
        email: form.email.trim(),
        password: form.password,
        fullName: form.fullName.trim(),
        phone: form.phone.trim() || null,
        preferredLanguage: language,
      });
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
          <AppText variant="h1">{t('auth.registerTitle')}</AppText>

          {formError ? (
            <View
              style={[
                styles.banner,
                {backgroundColor: theme.colors.surfaceAlt, borderColor: theme.colors.danger},
              ]}>
              <AppText variant="caption" color={theme.colors.danger} testID="register-error">
                {t(formError)}
              </AppText>
            </View>
          ) : null}

          <Input
            testID="register-name"
            label={t('auth.fullName')}
            required
            value={form.fullName}
            onChangeText={value => update('fullName', value)}
            autoCapitalize="words"
            error={errors.fullName ? t(errors.fullName) : undefined}
          />

          <Input
            testID="register-email"
            label={t('auth.email')}
            required
            value={form.email}
            onChangeText={value => update('email', value)}
            placeholder={t('auth.emailPlaceholder')}
            keyboardType="email-address"
            autoCapitalize="none"
            autoCorrect={false}
            error={errors.email ? t(errors.email) : undefined}
          />

          <Input
            testID="register-phone"
            label={t('auth.phone')}
            hint={t('common.optional')}
            value={form.phone}
            onChangeText={value => update('phone', value)}
            keyboardType="phone-pad"
          />

          <Input
            testID="register-password"
            label={t('auth.password')}
            required
            hint={t('auth.passwordRule')}
            value={form.password}
            onChangeText={value => update('password', value)}
            secureTextEntry
            autoCapitalize="none"
            error={errors.password ? t(errors.password) : undefined}
          />

          <Input
            testID="register-confirm"
            label={t('auth.confirmPassword')}
            required
            value={form.confirm}
            onChangeText={value => update('confirm', value)}
            secureTextEntry
            autoCapitalize="none"
            error={errors.confirm ? t(errors.confirm) : undefined}
          />

          <Button
            testID="register-submit"
            title={t('auth.register')}
            onPress={onSubmit}
            loading={submitting}
          />

          <Button
            testID="register-go-login"
            title={t('auth.haveAccount')}
            variant="ghost"
            onPress={() => navigation.navigate('Login')}
            style={styles.switch}
          />
        </ScrollView>
      </KeyboardAvoidingView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  flex: {flex: 1},
  content: {padding: 24, paddingTop: 32},
  banner: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 8,
    padding: 12,
    marginTop: 16,
  },
  switch: {marginTop: 10},
});
