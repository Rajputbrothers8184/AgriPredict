import React, {useCallback, useMemo} from 'react';
import {Alert, RefreshControl, ScrollView, StyleSheet, View} from 'react-native';

import {
  AppText,
  Badge,
  Button,
  Card,
  Divider,
  ErrorState,
  LoadingState,
  Row,
  Screen,
} from '../../components/ui';
import {useTheme} from '../../context/ThemeContext';
import {useTranslation} from '../../context/LocalizationContext';
import {useAsync} from '../../hooks/useAsync';
import {commodityName, cropApi} from '../../services/api';
import {
  CROP_STATUSES,
  EXPENSE_CATEGORIES,
  SEASONS,
  labelKeyFor,
  toneForStatus,
} from '../../constants/options';
import {
  formatArea,
  formatDate,
  formatPercent,
  formatPriceWithUnit,
  formatQuantityKg,
  toNumber,
} from '../../utils/format';
import {breakEvenPricePerMaund, profitSummary} from '../../utils/finance';

export default function CropDetailScreen({navigation, route}) {
  const {theme} = useTheme();
  const {t, language} = useTranslation();
  const {cropId} = route.params || {};

  const load = useCallback(async () => {
    // The detail route already carries the server-computed `finance` block;
    // the two lists are fetched for the itemised sections.
    const [cycle, expenses, sales] = await Promise.all([
      cropApi.get(cropId),
      cropApi.expenses(cropId),
      cropApi.sales(cropId),
    ]);
    return {
      cycle,
      expenses: Array.isArray(expenses) ? expenses : [],
      sales: Array.isArray(sales) ? sales : [],
    };
  }, [cropId]);

  const {data, error, loading, run} = useAsync(load);

  // Prefer the server's FinanceSummary; fall back to the local calculation if
  // the block is absent (older deployment) so the screen never shows blanks.
  const summary = useMemo(() => {
    if (!data) {
      return null;
    }
    const server = data.cycle && data.cycle.finance;
    if (server) {
      return {
        revenue: toNumber(server.revenue_pkr) || 0,
        cost: toNumber(server.cost_pkr) || 0,
        profit: toNumber(server.profit_pkr) || 0,
        margin: toNumber(server.margin_pct),
        isProfit: (toNumber(server.profit_pkr) || 0) >= 0,
        breakEven: toNumber(server.break_even_price_pkr),
      };
    }
    const local = profitSummary({expenses: data.expenses, sales: data.sales});
    return {
      ...local,
      breakEven: breakEvenPricePerMaund({
        expenses: data.expenses,
        sales: data.sales,
        expectedYieldKg: data.cycle && data.cycle.expected_yield_kg,
      }),
    };
  }, [data]);

  function confirmDelete(kind, itemId) {
    const message = kind === 'expense' ? t('expenses.deleteConfirm') : t('sales.deleteConfirm');
    Alert.alert(message, '', [
      {text: t('common.cancel'), style: 'cancel'},
      {
        text: t('common.delete'),
        style: 'destructive',
        onPress: async () => {
          try {
            if (kind === 'expense') {
              await cropApi.removeExpense(cropId, itemId);
            } else {
              await cropApi.removeSale(cropId, itemId);
            }
            run();
          } catch {
            Alert.alert(t('common.somethingWentWrong'));
          }
        },
      },
    ]);
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

  const cycle = (data && data.cycle) || {};
  const expenses = (data && data.expenses) || [];
  const sales = (data && data.sales) || [];

  return (
    <Screen>
      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={run} />}>
        <Card>
          <View style={styles.headerRow}>
            <AppText variant="h2" style={styles.flex}>
              {commodityName(cycle.commodity, language)}
            </AppText>
            <Badge
              label={t(labelKeyFor(CROP_STATUSES, cycle.status, 'crops.statusActive'))}
              tone={toneForStatus(cycle.status)}
            />
          </View>
          <AppText variant="caption" color={theme.colors.textMuted} style={styles.meta}>
            {formatArea(cycle.area_acres)} ·{' '}
            {t(labelKeyFor(SEASONS, cycle.season, 'crops.seasonRabi'))}
          </AppText>
          <Divider />
          <Row label={t('crops.sowingDate')} value={formatDate(cycle.sowing_date)} />
          <Row label={t('crops.expectedHarvest')} value={formatDate(cycle.expected_harvest_date)} />
          <Row label={t('crops.expectedYield')} value={formatQuantityKg(cycle.expected_yield_kg)} />
          {cycle.actual_yield_kg ? (
            <Row label={t('crops.actualYield')} value={formatQuantityKg(cycle.actual_yield_kg)} />
          ) : null}
        </Card>

        <Card>
          <AppText variant="h3">{t('crops.profit')}</AppText>
          <Row label={t('crops.revenue')} value={formatPriceWithUnit(summary.revenue)} />
          <Row label={t('crops.cost')} value={formatPriceWithUnit(summary.cost)} />
          <Divider />
          <Row
            label={t('crops.profit')}
            value={formatPriceWithUnit(summary.profit)}
            strong
            tone={summary.isProfit ? 'profit' : 'loss'}
          />
          <Row
            label={t('crops.margin')}
            value={summary.margin === null ? '—' : formatPercent(summary.margin)}
          />
          {summary.breakEven !== null ? (
            <Row label={t('crops.breakEven')} value={formatPriceWithUnit(summary.breakEven)} />
          ) : null}
        </Card>

        <Card>
          <View style={styles.headerRow}>
            <AppText variant="h3" style={styles.flex}>
              {t('expenses.title')}
            </AppText>
            <Button
              title={t('common.add')}
              variant="secondary"
              style={styles.smallButton}
              onPress={() => navigation.navigate('ExpenseForm', {cropId})}
            />
          </View>
          {expenses.length === 0 ? (
            <AppText variant="caption" color={theme.colors.textMuted} style={styles.empty}>
              {t('expenses.empty')}
            </AppText>
          ) : (
            expenses.map(expense => (
              <View key={expense.id} style={styles.lineItem}>
                <View style={styles.flex}>
                  <AppText variant="bodyStrong">
                    {t(labelKeyFor(EXPENSE_CATEGORIES, expense.category, 'expenses.catOther'))}
                  </AppText>
                  <AppText variant="tiny" color={theme.colors.textMuted}>
                    {formatDate(expense.expense_date)}
                    {expense.description ? ` · ${expense.description}` : ''}
                  </AppText>
                </View>
                <AppText variant="bodyStrong">{formatPriceWithUnit(expense.amount_pkr)}</AppText>
                <Button
                  testID={`delete-expense-${expense.id}`}
                  title="✕"
                  variant="ghost"
                  style={styles.deleteButton}
                  onPress={() => confirmDelete('expense', expense.id)}
                />
              </View>
            ))
          )}
        </Card>

        <Card>
          <View style={styles.headerRow}>
            <AppText variant="h3" style={styles.flex}>
              {t('sales.title')}
            </AppText>
            <Button
              title={t('common.add')}
              variant="secondary"
              style={styles.smallButton}
              onPress={() => navigation.navigate('SaleForm', {cropId})}
            />
          </View>
          {sales.length === 0 ? (
            <AppText variant="caption" color={theme.colors.textMuted} style={styles.empty}>
              {t('sales.empty')}
            </AppText>
          ) : (
            sales.map(sale => (
              <View key={sale.id} style={styles.lineItem}>
                <View style={styles.flex}>
                  <AppText variant="bodyStrong">
                    {formatQuantityKg(sale.quantity_kg)} @ {formatPriceWithUnit(sale.unit_price_pkr)}
                  </AppText>
                  <AppText variant="tiny" color={theme.colors.textMuted}>
                    {formatDate(sale.sale_date)}
                    {sale.buyer_name ? ` · ${sale.buyer_name}` : ''}
                  </AppText>
                </View>
                <AppText variant="bodyStrong">
                  {formatPriceWithUnit(sale.total_amount_pkr)}
                </AppText>
                <Button
                  testID={`delete-sale-${sale.id}`}
                  title="✕"
                  variant="ghost"
                  style={styles.deleteButton}
                  onPress={() => confirmDelete('sale', sale.id)}
                />
              </View>
            ))
          )}
        </Card>

        <Button
          title={t('crops.editTitle')}
          variant="secondary"
          onPress={() => navigation.navigate('CropForm', {mode: 'edit', cropId})}
        />
        <Button
          title={t('reports.cropCycleReport')}
          variant="ghost"
          onPress={() => navigation.navigate('Reports', {cropId})}
          style={styles.secondaryAction}
        />
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: {padding: 16, paddingBottom: 40},
  headerRow: {flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 4},
  flex: {flex: 1},
  meta: {marginBottom: 8},
  empty: {paddingVertical: 12},
  lineItem: {flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 10},
  smallButton: {minHeight: 34, paddingHorizontal: 12},
  deleteButton: {minHeight: 30, minWidth: 34, paddingHorizontal: 6},
  secondaryAction: {marginTop: 10},
});
