import React, {useCallback, useState} from 'react';
import {KeyboardAvoidingView, Platform, ScrollView, StyleSheet} from 'react-native';

import {AppText, Button, Card, ErrorState, Input, LoadingState, Screen} from '../components/ui';
import {useTheme} from '../context/ThemeContext';
import {useTranslation} from '../context/LocalizationContext';
import {useAsync} from '../hooks/useAsync';
import {farmApi} from '../services/api';
import {mapApiError} from '../utils/errors';
import {toNumber} from '../utils/format';
import {optionalPositiveNumber, required, validateForm} from '../utils/validation';

/**
 * Create or edit a farm.
 *
 * FarmCreate fields: name, district, tehsil, latitude, longitude,
 * total_area_acres. The API requires latitude and longitude to be supplied
 * together, so the form validates that pair locally rather than letting the
 * request fail with a 422.
 */
export default function FarmFormScreen({navigation, route}) {
  const {theme} = useTheme();
  const {t} = useTranslation();
  const params = route.params || {};
  const isEdit = params.mode === 'edit';

  const load = useCallback(
    async () => (isEdit && params.farmId ? farmApi.get(params.farmId) : null),
    [isEdit, params.farmId],
  );
  const {data, error, loading, run} = useAsync(load);

  const [form, setForm] = useState({
    name: '',
    district: '',
    tehsil: '',
    areaAcres: '',
    latitude: '',
    longitude: '',
  });
  const [hydrated, setHydrated] = useState(!isEdit);
  const [errors, setErrors] = useState({});
  const [submitError, setSubmitError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  // Populate once for edit mode; never overwrite what the user has typed.
  if (!hydrated && data) {
    setHydrated(true);
    setForm({
      name: data.name || '',
      district: data.district || '',
      tehsil: data.tehsil || '',
      areaAcres:
        data.total_area_acres !== null && data.total_area_acres !== undefined
          ? String(data.total_area_acres)
          : '',
      latitude: data.latitude !== null && data.latitude !== undefined ? String(data.latitude) : '',
      longitude:
        data.longitude !== null && data.longitude !== undefined ? String(data.longitude) : '',
    });
  }

  function update(key, value) {
    setForm(previous => ({...previous, [key]: value}));
  }

  async function onSubmit() {
    const hasLat = form.latitude.trim() !== '';
    const hasLng = form.longitude.trim() !== '';
    const {errors: nextErrors, valid} = validateForm(form, {
      name: required,
      district: required,
      areaAcres: optionalPositiveNumber,
      // Coordinates must be supplied as a pair (the API rejects one alone).
      latitude: value => (hasLat !== hasLng ? 'validation.required' : null),
      longitude: () => (hasLat !== hasLng ? 'validation.required' : null),
    });
    setErrors(
      Object.fromEntries(Object.entries(nextErrors).filter(([, value]) => Boolean(value))),
    );
    setSubmitError(null);
    if (!valid) {
      return;
    }

    const payload = {
      name: form.name.trim(),
      district: form.district.trim(),
      tehsil: form.tehsil.trim() || null,
      total_area_acres: form.areaAcres ? toNumber(form.areaAcres) : null,
      latitude: hasLat ? toNumber(form.latitude) : null,
      longitude: hasLng ? toNumber(form.longitude) : null,
    };

    setSubmitting(true);
    try {
      if (isEdit) {
        await farmApi.update(params.farmId, payload);
      } else {
        await farmApi.create(payload);
      }
      navigation.goBack();
    } catch (caught) {
      setSubmitError(mapApiError(caught).messageKey);
    } finally {
      setSubmitting(false);
    }
  }

  if (isEdit && loading && !data) {
    return (
      <Screen>
        <LoadingState />
      </Screen>
    );
  }

  if (isEdit && error && !data) {
    return (
      <Screen>
        <ErrorState message={t(error.messageKey)} onRetry={run} />
      </Screen>
    );
  }

  return (
    <Screen>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          {submitError ? (
            <AppText variant="caption" color={theme.colors.danger} style={styles.banner}>
              {t(submitError)}
            </AppText>
          ) : null}

          <Card>
            <Input
              testID="farm-name"
              label={t('crops.farm')}
              required
              value={form.name}
              onChangeText={value => update('name', value)}
              error={errors.name ? t(errors.name) : undefined}
            />
            <Input
              testID="farm-district"
              label={t('sales.market') === '' ? 'District' : 'District'}
              required
              value={form.district}
              onChangeText={value => update('district', value)}
              placeholder="Lahore"
              error={errors.district ? t(errors.district) : undefined}
            />
            <Input
              label="Tehsil"
              hint={t('common.optional')}
              value={form.tehsil}
              onChangeText={value => update('tehsil', value)}
            />
            <Input
              testID="farm-area"
              label={`${t('crops.areaAcres')} · ${t('common.optional')}`}
              value={form.areaAcres}
              onChangeText={value => update('areaAcres', value)}
              keyboardType="decimal-pad"
              error={errors.areaAcres ? t(errors.areaAcres) : undefined}
            />
          </Card>

          <Card>
            <AppText variant="caption" color={theme.colors.textMuted}>
              {t('weather.addCoordinates')}
            </AppText>
            <Input
              label="Latitude"
              hint={t('common.optional')}
              value={form.latitude}
              onChangeText={value => update('latitude', value)}
              keyboardType="numbers-and-punctuation"
              placeholder="31.5204"
              error={errors.latitude ? t(errors.latitude) : undefined}
            />
            <Input
              label="Longitude"
              hint={t('common.optional')}
              value={form.longitude}
              onChangeText={value => update('longitude', value)}
              keyboardType="numbers-and-punctuation"
              placeholder="74.3587"
              error={errors.longitude ? t(errors.longitude) : undefined}
            />
          </Card>

          <Button
            testID="farm-submit"
            title={t('common.save')}
            onPress={onSubmit}
            loading={submitting}
          />
          <Button
            title={t('common.cancel')}
            variant="ghost"
            onPress={() => navigation.goBack()}
            style={styles.cancel}
          />
        </ScrollView>
      </KeyboardAvoidingView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  flex: {flex: 1},
  content: {padding: 16, paddingBottom: 40},
  banner: {marginBottom: 12},
  cancel: {marginTop: 10},
});
