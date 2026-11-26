import React, {useCallback, useMemo} from 'react';
import {RefreshControl, ScrollView, StyleSheet, View} from 'react-native';

import {
  AppText,
  Button,
  Card,
  ErrorState,
  LoadingState,
  Row,
  Screen,
  StatTile,
} from '../components/ui';
import PriceChart from '../components/PriceChart';
import {useAuth} from '../context/AuthContext';
import {useTheme} from '../context/ThemeContext';
import {useTranslation} from '../context/LocalizationContext';
import {useAsync} from '../hooks/useAsync';
import {cropApi, farmApi, financeApi, forecastApi, marketApi} from '../services/api';
import {
  formatArea,
  formatDate,
  formatPercent,
  formatPriceWithUnit,
  toNumber,
} from '../utils/format';
import {profitSummary, totalAreaAcres} from '../utils/finance';

/** The dashboard highlights wheat in Lahore — the series used for validation. */
const HIGHLIGHT = {commodity: 'wheat', market: 'lahore-sabzi-mandi'};

export default function DashboardScreen({navigation}) {
  const {theme} = useTheme();
  const {t} = useTranslation();
  const {user} = useAuth();

  const load = useCallback(async () => {
    // allSettled: one unavailable section must not blank the whole dashboard.
    const [farms, cycles, finance, history, forecast] = await Promise.allSettled([
      farmApi.list(),
      cropApi.list(),
      financeApi.summary(),
      marketApi.history(HIGHLIGHT.commodity, HIGHLIGHT.market, 90),
      forecastApi.get(HIGHLIGHT.commodity, HIGHLIGHT.market, 7),
    ]);

    return {
      farms: farms.status === 'fulfilled' ? farms.value : [],
      cycles: cycles.status === 'fulfilled' ? cycles.value : [],
      finance: finance.status === 'fulfilled' ? finance.value : null,
      history: history.status === 'fulfilled' ? history.value : null,
      forecast: forecast.status === 'fulfilled' ? forecast.value : null,
    };
  }, []);

  const {data, error, loading, run} = useAsync(load);

  const summary = useMemo(() => {
    if (!data) {
      return null;
    }
    const active = (data.cycles || []).filter(cycle => cycle.status === 'active');
    const profit = data.finance
      ? {
          profit: toNumber(data.finance.lifetime_profit_pkr) || 0,
          margin: toNumber(data.finance.margin_pct),
          isProfit: (toNumber(data.finance.lifetime_profit_pkr) || 0) >= 0,
        }
      : profitSummary({expenses: [], sales: []});
    return {
      activeCount: active.length,
      area: totalAreaAcres(data.cycles || []),
      profit,
    };
  }, [data]);

  const series = useMemo(() => {
    const points = (data && data.history && data.history.points) || [];
    return points
      .slice(-30)
      .map(point => ({date: point.price_date, value: toNumber(point.avg_price_pkr)}));
  }, [data]);

  const forecastPoints = useMemo(() => {
    const points = (data && data.forecast && data.forecast.points) || [];
    return points.map(point => ({
      date: point.target_date,
      value: toNumber(point.predicted_price_pkr),
      lower: toNumber(point.lower_bound_pkr),
      upper: toNumber(point.upper_bound_pkr),
    }));
  }, [data]);

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

  const firstName = ((user && user.full_name) || '').split(' ')[0];
  const latest = series.length > 0 ? series[series.length - 1] : null;
  const change =
    series.length > 1
      ? ((latest.value - series[0].value) / series[0].value) * 100
      : null;
  const isSynthetic =
    Boolean(
      data &&
        data.history &&
        (data.history.points || []).some(point => point.source === 'synthetic_fixture'),
    );

  return (
    <Screen>
      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={
          <RefreshControl
            refreshing={loading}
            onRefresh={run}
            tintColor={theme.colors.primary}
          />
        }>
        <AppText variant="h1">{t('dashboard.greeting', {name: firstName || ''})}</AppText>
        <AppText variant="caption" color={theme.colors.textMuted} style={styles.subtitle}>
          {t('dashboard.subtitle')}
        </AppText>

        <View style={styles.tiles}>
          <StatTile
            label={t('dashboard.activeCrops')}
            value={summary ? String(summary.activeCount) : '—'}
          />
          <StatTile
            label={t('dashboard.totalArea')}
            value={summary ? formatArea(summary.area) : '—'}
          />
        </View>

        <View style={styles.tiles}>
          <StatTile
            label={t('dashboard.seasonProfit')}
            value={summary ? formatPriceWithUnit(summary.profit.profit) : '—'}
            tone={summary && summary.profit.isProfit ? 'profit' : 'loss'}
            hint={
              summary && summary.profit.margin !== null
                ? `${t('finance.margin')}: ${formatPercent(summary.profit.margin)}`
                : undefined
            }
          />
          <StatTile
            label={t('dashboard.latestPrice')}
            value={latest ? formatPriceWithUnit(latest.value) : '—'}
            hint={change !== null ? `${t('market.change7d')}: ${formatPercent(change)}` : undefined}
            tone={change === null ? undefined : change >= 0 ? 'profit' : 'loss'}
          />
        </View>

        <Card>
          <View style={styles.cardHeader}>
            <AppText variant="h3">{t('market.history')}</AppText>
            {isSynthetic ? (
              <AppText variant="tiny" color={theme.colors.warning}>
                {t('market.sourceSynthetic')}
              </AppText>
            ) : null}
          </View>

          {series.length === 0 ? (
            <View style={styles.chartEmpty}>
              <AppText variant="caption" color={theme.colors.textMuted}>
                {t('market.noData')}
              </AppText>
            </View>
          ) : (
            <PriceChart series={series} forecast={forecastPoints} width={320} />
          )}

          <Row
            label={t('market.unit')}
            value={latest ? formatDate(latest.date) : '—'}
          />
        </Card>

        <Card>
          <AppText variant="h3">{t('dashboard.quickActions')}</AppText>
          <View style={styles.actions}>
            <Button
              title={t('dashboard.addCrop')}
              variant="secondary"
              style={styles.action}
              onPress={() =>
                navigation.navigate('CropForm', {
                  mode: 'create',
                  farms: (data && data.farms) || [],
                })
              }
            />
            <Button
              title={t('dashboard.viewMarket')}
              variant="secondary"
              style={styles.action}
              onPress={() => navigation.navigate('MarketTab')}
            />
          </View>
          <View style={styles.actions}>
            <Button
              title={t('buyers.title')}
              variant="secondary"
              style={styles.action}
              onPress={() => navigation.navigate('Buyers')}
            />
            <Button
              title={t('reports.title')}
              variant="secondary"
              style={styles.action}
              onPress={() => navigation.navigate('Reports')}
            />
          </View>
        </Card>

        {data && data.farms.length === 0 ? (
          <Card>
            <AppText variant="h3">{t('dashboard.noFarmTitle')}</AppText>
            <AppText variant="caption" color={theme.colors.textMuted} style={styles.hint}>
              {t('dashboard.noFarmBody')}
            </AppText>
            <Button
              testID="dashboard-add-farm"
              title={t('common.add')}
              onPress={() => navigation.navigate('FarmForm')}
              style={styles.addFarm}
            />
          </Card>
        ) : null}
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: {padding: 16, paddingBottom: 32},
  subtitle: {marginTop: 4, marginBottom: 16},
  tiles: {flexDirection: 'row', gap: 12, marginBottom: 12},
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  chartEmpty: {paddingVertical: 40, alignItems: 'center'},
  actions: {flexDirection: 'row', gap: 10, marginTop: 10},
  action: {flex: 1},
  hint: {marginTop: 6},
  addFarm: {marginTop: 14},
});
