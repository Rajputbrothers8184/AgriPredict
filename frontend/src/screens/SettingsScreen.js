import React, {useState} from 'react';
import {Alert, ScrollView, StyleSheet, View} from 'react-native';

import {AppText, Button, Card, Input, Screen} from '../components/ui';
import {APP_VERSION} from '../config';
import {useAuth} from '../context/AuthContext';
import {useTheme} from '../context/ThemeContext';
import {useTranslation} from '../context/LocalizationContext';
import {mapApiError} from '../utils/errors';
import {passwordsMatch, required, validPassword} from '../utils/validation';

const THEME_OPTIONS = [
  {value: 'light', labelKey: 'settings.themeLight'},
  {value: 'dark', labelKey: 'settings.themeDark'},
  {value: 'system', labelKey: 'settings.themeSystem'},
];

export default function SettingsScreen() {
  const {theme, preference, setTheme} = useTheme();
  const {t, language, setLanguage} = useTranslation();
  const {changePassword} = useAuth();

  const [showPasswordForm, setShowPasswordForm] = useState(false);
  const [form, setForm] = useState({current: '', next: '', confirm: ''});
  const [errors, setErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);

  async function onPasswordSubmit() {
    const nextErrors = {
      current: required(form.current),
      next: validPassword(form.next),
      confirm: passwordsMatch(form.next, form.confirm),
    };
    const cleaned = Object.fromEntries(
      Object.entries(nextErrors).filter(([, value]) => Boolean(value)),
    );
    setErrors(cleaned);
    if (Object.keys(cleaned).length > 0) {
      return;
    }

    setSubmitting(true);
    try {
      await changePassword({currentPassword: form.current, newPassword: form.next});
      Alert.alert(t('settings.passwordChanged'));
    } catch (caught) {
      Alert.alert(t(mapApiError(caught).messageKey));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.content}>
        <Card>
          <AppText variant="h3">{t('settings.language')}</AppText>
          <View style={styles.row}>
            <Button
              testID="language-en"
              title={t('settings.english')}
              variant={language === 'en' ? 'primary' : 'secondary'}
              onPress={() => setLanguage('en')}
              style={styles.chip}
            />
            <Button
              testID="language-ur"
              title={t('settings.urdu')}
              variant={language === 'ur' ? 'primary' : 'secondary'}
              onPress={() => setLanguage('ur')}
              style={styles.chip}
            />
          </View>
          <AppText variant="tiny" color={theme.colors.textMuted}>
            {language === 'ur'
              ? 'مکمل دائیں سے بائیں ترتیب اگلی بار ایپ کھلنے پر لاگو ہوگی۔'
              : 'Full right-to-left layout applies the next time the app starts.'}
          </AppText>
        </Card>

        <Card>
          <AppText variant="h3">{t('settings.theme')}</AppText>
          <View style={styles.row}>
            {THEME_OPTIONS.map(option => (
              <Button
                key={option.value}
                testID={`theme-${option.value}`}
                title={t(option.labelKey)}
                variant={preference === option.value ? 'primary' : 'secondary'}
                onPress={() => setTheme(option.value)}
                style={styles.chip}
              />
            ))}
          </View>
        </Card>

        <Card>
          <AppText variant="h3">{t('settings.account')}</AppText>
          {!showPasswordForm ? (
            <Button
              testID="settings-change-password"
              title={t('settings.changePassword')}
              variant="secondary"
              onPress={() => setShowPasswordForm(true)}
              style={styles.action}
            />
          ) : (
            <View style={styles.passwordForm}>
              <Input
                label={t('settings.currentPassword')}
                secureTextEntry
                value={form.current}
                onChangeText={value => setForm(previous => ({...previous, current: value}))}
                error={errors.current ? t(errors.current) : undefined}
              />
              <Input
                label={t('settings.newPassword')}
                secureTextEntry
                hint={t('auth.passwordRule')}
                value={form.next}
                onChangeText={value => setForm(previous => ({...previous, next: value}))}
                error={errors.next ? t(errors.next) : undefined}
              />
              <Input
                label={t('auth.confirmPassword')}
                secureTextEntry
                value={form.confirm}
                onChangeText={value => setForm(previous => ({...previous, confirm: value}))}
                error={errors.confirm ? t(errors.confirm) : undefined}
              />
              <Button
                title={t('common.save')}
                onPress={onPasswordSubmit}
                loading={submitting}
              />
              <Button
                title={t('common.cancel')}
                variant="ghost"
                onPress={() => setShowPasswordForm(false)}
                style={styles.action}
              />
            </View>
          )}
        </Card>

        <Card>
          <AppText variant="h3">{t('settings.about')}</AppText>
          <AppText variant="caption" color={theme.colors.textMuted} style={styles.about}>
            {t('settings.aboutBody')}
          </AppText>
          <AppText variant="tiny" color={theme.colors.textMuted}>
            {t('settings.version')} {APP_VERSION}
          </AppText>
        </Card>
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: {padding: 16, paddingBottom: 40},
  row: {flexDirection: 'row', gap: 8, marginVertical: 12},
  chip: {flex: 1},
  action: {marginTop: 10},
  passwordForm: {marginTop: 12},
  about: {marginVertical: 8},
});
