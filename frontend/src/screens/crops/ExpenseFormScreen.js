import React, {useState} from 'react';
import {KeyboardAvoidingView, Platform, ScrollView, StyleSheet} from 'react-native';

import {AppText, Button, Card, Input, Screen} from '../../components/ui';
import {useTheme} from '../../context/ThemeContext';
import {useTranslation} from '../../context/LocalizationContext';
import {cropApi} from '../../services/api';
import {EXPENSE_CATEGORIES} from '../../constants/options';
import {mapApiError} from '../../utils/errors';
import {toNumber, todayIso} from '../../utils/format';
import {isoDate, positiveNumber, validateForm} from '../../utils/validation';
import {ChoiceRow} from './CropFormScreen';

export default function ExpenseFormScreen({navigation, route}) {
  const {theme} = useTheme();
  const {t} = useTranslation();
  const {cropId} = route.params || {};

  const [form, setForm] = useState({
    category: 'seeds',
    amount: '',
    date: todayIso(),
    description: '',
  });
  const [errors, setErrors] = useState({});
  const [submitError, setSubmitError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  function update(key, value) {
    setForm(previous => ({...previous, [key]: value}));
  }

  async function onSubmit() {
    const {errors: nextErrors, valid} = validateForm(form, {
      amount: positiveNumber,
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
      // ExpenseCreate: category, amount_pkr, expense_date, description.
      await cropApi.addExpense(cropId, {
        category: form.category,
        amount_pkr: toNumber(form.amount),
        expense_date: form.date,
        description: form.description.trim() || null,
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
            <AppText variant="caption" color={theme.colors.textMuted} style={styles.label}>
              {t('expenses.category')}
            </AppText>
            <ChoiceRow
              options={EXPENSE_CATEGORIES.map(option => ({
                value: option.value,
                label: t(option.labelKey),
              }))}
              value={form.category}
              onChange={value => update('category', value)}
              testIDPrefix="expense-category"
            />

            <Input
              testID="expense-amount"
              label={`${t('expenses.amount')} (PKR)`}
              required
              value={form.amount}
              onChangeText={value => update('amount', value)}
              keyboardType="decimal-pad"
              error={errors.amount ? t(errors.amount) : undefined}
            />
            <Input
              testID="expense-date"
              label={t('expenses.date')}
              required
              value={form.date}
              onChangeText={value => update('date', value)}
              placeholder="2026-11-25"
              error={errors.date ? t(errors.date) : undefined}
            />
            <Input
              label={t('expenses.description')}
              hint={t('common.optional')}
              value={form.description}
              onChangeText={value => update('description', value)}
            />
          </Card>

          <Button
            testID="expense-submit"
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
  label: {marginBottom: 8},
  banner: {marginBottom: 12},
  cancel: {marginTop: 10},
});
