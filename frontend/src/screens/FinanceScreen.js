import React, {useCallback} from 'react';
import {RefreshControl, ScrollView, StyleSheet, View} from 'react-native';

import {
  AppText,
  Card,
  Divider,
  EmptyState,
  ErrorState,
  LoadingState,
  Row,
  Screen,
  StatTile,
} from '../components/ui';
import {useTheme} from '../context/ThemeContext';
import {useTranslation} from '../context/LocalizationContext';
import {useAsync} from '../hooks/useAsync';
import {cropApi, financeApi} from '../services/api';
import {EXPENSE_CATEGORIES, SEASONS, labelKeyFor} from '../constants/options';
import {formatArea, formatPercent, formatPrice, formatPriceWithUnit, toNumber} from '../utils/format';
import {normaliseBreakdown} from '../utils/finance';

/**
 * Finance tab.
 *
 * Figures come from `/finance/summary` (FinanceOverview), which already
 * aggregates lifetime revenue, cost, profit, margin, per-season rows and the
 * expense breakdown server-side. The app does not recompute them, so the screen
 * and the exported PDF/XLSX statement can never disagree.
 */
export default function FinanceScreen() {
  const {theme} = useTheme();
  const {t} = useTranslation();

  const load = useCallback(async () => {
    const [overview, cycles] = await Promise.allSettled([
      financeApi.summary(),
      cropApi.list(),
    ]);
    return {
      overview: overview.status === 'fulfilled' ? overview.value : null,
      cycles: cycles.status === 'fulfilled' ? cycles.value : [],
    };
  }, []);

  const {data, error, loading, run} = useAsync(load);

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

  const overview = data && data.overview;
  const cycles = (data && data.cycles) || [];

  if (!overview || cycles.length === 0) {
    return (
      <Screen>
        <EmptyState
          testID="finance-empty"
          title={t('finance.noData')}
          body={t('finance.noDataHint')}
        />
      </Screen>
    );
  }

  const revenue = toNumber(overview.lifetime_revenue_pkr) || 0;
  const cost = toNumber(overview.lifetime_cost_pkr) || 0;
  const profit = toNumber(overview.lifetime_profit_pkr) || 0;
  const margin = toNumber(overview.margin_pct);
  const breakdown = normaliseBreakdown(overview.expense_breakdown || []);

  return (
    <Screen>
      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={run} />}>
        <View style={styles.tiles}>
          <StatTile label={t('finance.revenue')} value={formatPrice(revenue)} />
          <StatTile label={t('finance.cost')} value={formatPrice(cost)} />
        </View>

        <Card>
          <AppText variant="h3">{t('finance.summary')}</AppText>
          <Row
            label={t('finance.profit')}
            value={formatPriceWithUnit(profit)}
            strong
            tone={profit >= 0 ? 'profit' : 'loss'}
          />
          <Row label={t('finance.margin')} value={margin === null ? '—' : formatPercent(margin)} />
          <Row label={t('dashboard.activeCrops')} value={String(overview.active_cycles ?? 0)} />
        </Card>

        <Card>
          <AppText variant="h3">{t('finance.seasons')}</AppText>
          <Divider />
          {(overview.seasons || []).length === 0 ? (
            <AppText variant="caption" color={theme.colors.textMuted} style={styles.empty}>
              —
            </AppText>
          ) : (
            (overview.seasons || []).map(season => (
              <View key={`${season.season}-${season.year}`} style={styles.seasonRow}>
                <View style={styles.flex}>
                  <AppText variant="bodyStrong">
                    {t(labelKeyFor(SEASONS, season.season, 'crops.seasonRabi'))} {season.year}
                  </AppText>
                  <AppText variant="tiny" color={theme.colors.textMuted}>
                    {season.cycles} · {t('crops.title')} · {formatArea(season.total_area_acres)}
                  </AppText>
                </View>
                <View style={styles.alignEnd}>
                  <AppText
                    variant="bodyStrong"
                    color={
                      (toNumber(season.profit_pkr) || 0) >= 0
                        ? theme.colors.profit
                        : theme.colors.loss
                    }>
                    {formatPrice(season.profit_pkr)}
                  </AppText>
                  <AppText variant="tiny" color={theme.colors.textMuted}>
                    {toNumber(season.margin_pct) === null
                      ? '—'
                      : formatPercent(toNumber(season.margin_pct))}
                  </AppText>
                </View>
              </View>
            ))
          )}
        </Card>

        <Card>
          <AppText variant="h3">{t('finance.expenseMix')}</AppText>
          <Divider />
          {breakdown.map(row => (
            <View key={row.category} style={styles.categoryRow}>
              <View style={styles.flex}>
                <AppText variant="body">
                  {t(labelKeyFor(EXPENSE_CATEGORIES, row.category, 'expenses.catOther'))}
                </AppText>
                <View
                  style={[
                    styles.barTrack,
                    {backgroundColor: theme.colors.surfaceAlt, borderRadius: theme.radius.pill},
                  ]}>
                  <View
                    style={[
                      styles.barFill,
                      {
                        width: `${Math.max(row.share, 1)}%`,
                        backgroundColor: theme.colors.primary,
                        borderRadius: theme.radius.pill,
                      },
                    ]}
                  />
                </View>
              </View>
              <View style={styles.categoryValue}>
                <AppText variant="bodyStrong">{formatPrice(row.amount)}</AppText>
                <AppText variant="tiny" color={theme.colors.textMuted}>
                  {formatPercent(row.share, 0)}
                </AppText>
              </View>
            </View>
          ))}
        </Card>
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: {padding: 16, paddingBottom: 40},
  tiles: {flexDirection: 'row', gap: 12, marginBottom: 12},
  flex: {flex: 1},
  alignEnd: {alignItems: 'flex-end'},
  seasonRow: {flexDirection: 'row', alignItems: 'center', paddingVertical: 10, gap: 8},
  categoryRow: {flexDirection: 'row', alignItems: 'center', paddingVertical: 8, gap: 12},
  categoryValue: {alignItems: 'flex-end', minWidth: 84},
  barTrack: {height: 6, marginTop: 6, width: '100%', overflow: 'hidden'},
  barFill: {height: 6},
  empty: {paddingVertical: 12},
});
