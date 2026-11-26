import React, {useCallback, useEffect, useMemo, useState} from 'react';
import {KeyboardAvoidingView, Platform, ScrollView, StyleSheet, View} from 'react-native';

import {AppText, Button, Card, Input, Row, Screen} from '../../components/ui';
import {useTheme} from '../../context/ThemeContext';
import {useTranslation} from '../../context/LocalizationContext';
import {catalogueApi, cropApi} from '../../services/api';
import {mapApiError} from '../../utils/errors';
import {formatPriceWithUnit, toNumber, todayIso} from '../../utils/format';
import {KG_PER_MAUND} from '../../utils/finance';
import {isoDate, positiveNumber, validateForm} from '../../utils/validation';
import {ChoiceRow} from './CropFormScreen';

/**
 * Record a sale.
 *
 * total_amount_pkr is derived server-side (quantity_kg / 40 * unit_price_pkr),
 * so the app never posts a total; it only previews that multiplication, which is
 * the step farmers most often get wrong when prices are quoted per maund.
 */
export default function SaleFormScreen({navigation, route}) {
  const {theme} = useTheme();
  const {t} = useTranslation();
  const {cropId} = route.params || {};

  const [form, setForm] = useState({
    quantityKg: '',
    unitPrice: '',
    date: todayIso(),
    buyerName: '',
    marketId: '',
  });
  const [markets, setMarkets] = useState([]);
  const [errors, setErrors] = useState({});
  const [submitError, setSubmitError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  // Markets are optional context on a sale; a failure to load them must not
  // block recording the sale itself.
  const loadMarkets = useCallback(async () => {
    try {
      const result = await catalogueApi.markets();
      setMarkets(Array.isArray(result) ? result : []);
    } catch {
      setMarkets([]);
    }
  }, []);

  useEffect(() => {
    loadMarkets();
  }, [loadMarkets]);

  function update(key, value) {
    setForm(previous => ({...previous, [key]: value}));
  }

  const total = useMemo(() => {
    const kg = toNumber(form.quantityKg);
    const price = toNumber(form.unitPrice);
    if (kg === null || price === null) {
      return null;
    }
    return (kg / KG_PER_MAUND) * price;
  }, [form.quantityKg, form.unitPrice]);

  async function onSubmit() {
    const {errors: nextErrors, valid} = validateForm(form, {
      quantityKg: positiveNumber,
      unitPrice: positiveNumber,
      date: isoDate,
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
      await cropApi.addSale(cropId, {
        quantity_kg: toNumber(form.quantityKg),
        unit_price_pkr: toNumber(form.unitPrice),
        sale_date: form.date,
        market_id: form.marketId ? Number(form.marketId) : null,
        buyer_name: form.buyerName.trim() || null,
      });
      navigation.goBack();
    } catch (caught) {
      setSubmitError(mapApiError(caught).messageKey);
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
          {submitError ? (
            <AppText variant="caption" color={theme.colors.danger} style={styles.banner}>
              {t(submitError)}
            </AppText>
          ) : null}

          <Card>
            <Input
              testID="sale-quantity"
              label={t('sales.quantityKg')}
              required
              value={form.quantityKg}
              onChangeText={value => update('quantityKg', value)}
              keyboardType="decimal-pad"
              error={errors.quantityKg ? t(errors.quantityKg) : undefined}
            />
            <Input
              testID="sale-price"
              label={t('sales.pricePerMaund')}
              required
              value={form.unitPrice}
              onChangeText={value => update('unitPrice', value)}
              keyboardType="decimal-pad"
              error={errors.unitPrice ? t(errors.unitPrice) : undefined}
            />
            <Input
              testID="sale-date"
              label={t('sales.date')}
              required
              value={form.date}
              onChangeText={value => update('date', value)}
              placeholder="2026-11-25"
              error={errors.date ? t(errors.date) : undefined}
            />
            <Input
              testID="sale-buyer"
              label={t('sales.buyer')}
              hint={t('common.optional')}
              value={form.buyerName}
              onChangeText={value => update('buyerName', value)}
            />
          </Card>

          {markets.length > 0 ? (
            <Card>
              <AppText variant="caption" color={theme.colors.textMuted} style={styles.label}>
                {t('sales.market')} ({t('common.optional')})
              </AppText>
              <ChoiceRow
                options={markets.map(market => ({value: String(market.id), label: market.name}))}
                value={String(form.marketId)}
                onChange={value => update('marketId', value)}
                testIDPrefix="sale-market"
              />
            </Card>
          ) : null}

          <Card>
            <Row label={t('sales.total')} value={formatPriceWithUnit(total)} strong />
            <AppText variant="tiny" color={theme.colors.textMuted} style={styles.hint}>
              {t('sales.computedHint')}
            </AppText>
          </Card>

          <View>
            <Button
              testID="sale-submit"
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
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  flex: {flex: 1},
  content: {padding: 16, paddingBottom: 40},
  banner: {marginBottom: 12},
  label: {marginBottom: 8},
  hint: {marginTop: 4},
  cancel: {marginTop: 10},
});
