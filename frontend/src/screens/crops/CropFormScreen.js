import React, {useCallback, useMemo, useState} from 'react';
import {KeyboardAvoidingView, Platform, ScrollView, StyleSheet, View} from 'react-native';

import {AppText, Button, Card, ErrorState, Input, LoadingState, Screen} from '../../components/ui';
import {useTheme} from '../../context/ThemeContext';
import {useTranslation} from '../../context/LocalizationContext';
import {useAsync} from '../../hooks/useAsync';
import {catalogueApi, commodityName, cropApi, farmApi} from '../../services/api';
import {CROP_STATUSES, SEASONS, labelKeyFor} from '../../constants/options';
import {mapApiError} from '../../utils/errors';
import {formatDate, toNumber, todayIso} from '../../utils/format';
import {
  harvestAfterSowing,
  isoDate,
  optionalPositiveNumber,
  positiveNumber,
  required,
  validateForm,
} from '../../utils/validation';

/**
 * Create or edit a crop cycle.
 *
 * Route params: {mode: 'create'|'edit', cropId?, farms?}
 *
 * CropCycleCreate requires farm_id, commodity_id, area_acres and sowing_date;
 * farm_id and commodity_id are immutable after creation, so in edit mode only
 * the mutable fields are submitted (matching CropCycleUpdate).
 */
export default function CropFormScreen({navigation, route}) {
  const {theme} = useTheme();
  const {t, language} = useTranslation();
  const params = route.params || {};
  const isEdit = params.mode === 'edit';

  const load = useCallback(async () => {
    const [farms, commodities, existing] = await Promise.all([
      farmApi.list(),
      catalogueApi.commodities(),
      isEdit && params.cropId ? cropApi.get(params.cropId) : Promise.resolve(null),
    ]);
    return {farms, commodities, existing};
  }, [isEdit, params.cropId]);

  const {data, error, loading, run} = useAsync(load);

  const [form, setForm] = useState(null);
  const [errors, setErrors] = useState({});
  const [submitError, setSubmitError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const formValues = useMemo(() => {
    if (form) {
      return form;
    }
    if (!data) {
      return null;
    }
    const existing = data.existing || {};
    return {
      farmId: existing.farm_id ? String(existing.farm_id) : data.farms[0] ? String(data.farms[0].id) : '',
      commodityId:
        existing.commodity && existing.commodity.id ? String(existing.commodity.id) : '',
      season: existing.season || 'rabi',
      areaAcres: existing.area_acres ? String(existing.area_acres) : '',
      sowingDate: existing.sowing_date || todayIso(),
      expectedHarvest: existing.expected_harvest_date || '',
      actualHarvest: existing.actual_harvest_date || '',
      status: existing.status || 'active',
      expectedYield: existing.expected_yield_kg ? String(existing.expected_yield_kg) : '',
      actualYield: existing.actual_yield_kg ? String(existing.actual_yield_kg) : '',
      notes: existing.notes || '',
    };
  }, [form, data]);

  function update(key, value) {
    setForm(previous => ({...(previous || formValues), [key]: value}));
  }

  async function onSubmit() {
    const values = form || formValues;
    if (!values) {
      return;
    }

    const {errors: nextErrors, valid} = validateForm(values, {
      farmId: isEdit ? () => null : required,
      commodityId: isEdit ? () => null : required,
      areaAcres: positiveNumber,
      sowingDate: value => isoDate(value, {allowFuture: true}),
      expectedHarvest: value => (value ? harvestAfterSowing(values.sowingDate, value) : null),
      expectedYield: optionalPositiveNumber,
      actualYield: optionalPositiveNumber,
    });

    setErrors(
      Object.fromEntries(Object.entries(nextErrors).filter(([, value]) => Boolean(value))),
    );
    setSubmitError(null);
    if (!valid) {
      return;
    }

    setSubmitting(true);
    try {
      if (isEdit) {
        await cropApi.update(params.cropId, {
          season: values.season,
          area_acres: toNumber(values.areaAcres),
          sowing_date: values.sowingDate,
          expected_harvest_date: values.expectedHarvest || null,
          actual_harvest_date: values.actualHarvest || null,
          status: values.status,
          expected_yield_kg: values.expectedYield ? toNumber(values.expectedYield) : null,
          actual_yield_kg: values.actualYield ? toNumber(values.actualYield) : null,
          notes: values.notes.trim() || null,
        });
      } else {
        await cropApi.create({
          farm_id: Number(values.farmId),
          commodity_id: Number(values.commodityId),
          season: values.season,
          area_acres: toNumber(values.areaAcres),
          sowing_date: values.sowingDate,
          expected_harvest_date: values.expectedHarvest || null,
          status: values.status,
          expected_yield_kg: values.expectedYield ? toNumber(values.expectedYield) : null,
          notes: values.notes.trim() || null,
        });
      }
      navigation.goBack();
    } catch (caught) {
      setSubmitError(mapApiError(caught).messageKey);
    } finally {
      setSubmitting(false);
    }
  }

  if (loading && !data) {
    return (
      <Screen>
        <LoadingState />
      </Screen>
    );
  }

  if (error && !data) {
    return (
      <Screen>
        <ErrorState message={t(error.messageKey)} onRetry={run} />
      </Screen>
    );
  }

  if (!formValues) {
    return <Screen />;
  }

  const active = form || formValues;
  const farms = (data && data.farms) || [];
  const commodities = (data && data.commodities) || [];

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
            {isEdit ? (
              <AppText variant="caption" color={theme.colors.textMuted} style={styles.locked}>
                {t('crops.farm')} / {t('crops.commodity')}
              </AppText>
            ) : null}
            <AppText variant="caption" color={theme.colors.textMuted} style={styles.label}>
              {t('crops.farm')} *
            </AppText>
            <ChoiceRow
              options={farms.map(farm => ({value: String(farm.id), label: farm.name}))}
              value={String(active.farmId)}
              onChange={value => update('farmId', value)}
              emptyLabel={t('crops.selectFarm')}
              onEmpty={() => navigation.navigate('FarmForm')}
              testIDPrefix="farm-choice"
            />
            {errors.farmId ? (
              <AppText variant="tiny" color={theme.colors.danger}>
                {t(errors.farmId)}
              </AppText>
            ) : null}

            <AppText variant="caption" color={theme.colors.textMuted} style={styles.label}>
              {t('crops.commodity')} *
            </AppText>
            <ChoiceRow
              options={commodities.map(item => ({
                value: String(item.id),
                label: commodityName(item, language),
              }))}
              value={String(active.commodityId)}
              onChange={value => update('commodityId', value)}
              emptyLabel={t('crops.selectCrop')}
              testIDPrefix="commodity-choice"
            />
            {errors.commodityId ? (
              <AppText variant="tiny" color={theme.colors.danger}>
                {t(errors.commodityId)}
              </AppText>
            ) : null}

            <AppText variant="caption" color={theme.colors.textMuted} style={styles.label}>
              {t('crops.season')}
            </AppText>
            <ChoiceRow
              options={SEASONS.map(option => ({value: option.value, label: t(option.labelKey)}))}
              value={active.season}
              onChange={value => update('season', value)}
              testIDPrefix="season-choice"
            />
          </Card>

          <Card>
            <Input
              testID="crop-area"
              label={t('crops.areaAcres')}
              required
              value={active.areaAcres}
              onChangeText={value => update('areaAcres', value)}
              keyboardType="decimal-pad"
              error={errors.areaAcres ? t(errors.areaAcres) : undefined}
            />
            <Input
              testID="crop-sowing"
              label={t('crops.sowingDate')}
              required
              value={active.sowingDate}
              onChangeText={value => update('sowingDate', value)}
              placeholder="2026-11-25"
              hint={formatDate(active.sowingDate)}
              error={errors.sowingDate ? t(errors.sowingDate) : undefined}
            />
            <Input
              testID="crop-expected-harvest"
              label={t('crops.expectedHarvest')}
              hint={t('common.optional')}
              value={active.expectedHarvest}
              onChangeText={value => update('expectedHarvest', value)}
              placeholder="2027-04-10"
              error={errors.expectedHarvest ? t(errors.expectedHarvest) : undefined}
            />
            <Input
              testID="crop-expected-yield"
              label={t('crops.expectedYield')}
              hint={t('common.optional')}
              value={active.expectedYield}
              onChangeText={value => update('expectedYield', value)}
              keyboardType="number-pad"
              error={errors.expectedYield ? t(errors.expectedYield) : undefined}
            />
            {isEdit ? (
              <Input
                label={t('crops.actualYield')}
                hint={t('common.optional')}
                value={active.actualYield}
                onChangeText={value => update('actualYield', value)}
                keyboardType="number-pad"
                error={errors.actualYield ? t(errors.actualYield) : undefined}
              />
            ) : null}
          </Card>

          <Card>
            <AppText variant="caption" color={theme.colors.textMuted} style={styles.label}>
              {t('crops.status')}
            </AppText>
            <ChoiceRow
              options={CROP_STATUSES.map(option => ({
                value: option.value,
                label: t(labelKeyFor(CROP_STATUSES, option.value)),
              }))}
              value={active.status}
              onChange={value => update('status', value)}
              testIDPrefix="status-choice"
            />
            <Input
              label={t('crops.notes')}
              value={active.notes}
              onChangeText={value => update('notes', value)}
              multiline
              numberOfLines={3}
              style={styles.notes}
            />
          </Card>

          <Button
            testID="crop-submit"
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

/**
 * Horizontal single-select chips; no extra native picker dependency.
 *
 * `testIDPrefix` must be unique per row: a farm and a commodity can share the
 * same numeric id, and duplicate testIDs make an E2E selector ambiguous.
 */
export function ChoiceRow({options, value, onChange, emptyLabel, onEmpty, testIDPrefix = 'choice'}) {
  if (!options || options.length === 0) {
    return (
      <View style={styles.choiceWrap}>
        <Button
          title={emptyLabel || '—'}
          variant="secondary"
          onPress={onEmpty}
          style={styles.choiceEmpty}
        />
      </View>
    );
  }

  return (
    <View style={styles.choiceWrap}>
      {options.map(option => {
        const selected = String(option.value) === String(value);
        return (
          <Button
            key={option.value}
            testID={`${testIDPrefix}-${option.value}`}
            title={option.label}
            variant={selected ? 'primary' : 'secondary'}
            onPress={() => onChange(option.value)}
            style={styles.choice}
          />
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  flex: {flex: 1},
  content: {padding: 16, paddingBottom: 40},
  label: {marginBottom: 8, marginTop: 4},
  locked: {fontStyle: 'italic', marginBottom: 8},
  banner: {marginBottom: 12},
  choiceWrap: {flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 12},
  choice: {minHeight: 38, paddingHorizontal: 12},
  choiceEmpty: {minHeight: 38},
  notes: {minHeight: 80, textAlignVertical: 'top'},
  cancel: {marginTop: 10},
});
