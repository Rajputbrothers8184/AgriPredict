import React, {useCallback, useEffect, useMemo, useState} from 'react';
import {RefreshControl, ScrollView, StyleSheet, View} from 'react-native';

import {
  AppText,
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  Screen,
} from '../../components/ui';
import PriceChart from '../../components/PriceChart';
import {useTheme} from '../../context/ThemeContext';
import {useTranslation} from '../../context/LocalizationContext';
import {useAsync} from '../../hooks/useAsync';
import {catalogueApi, commodityName, forecastApi, marketApi} from '../../services/api';
import {formatDate, formatPercent, formatPrice, formatPriceWithUnit, toNumber} from '../../utils/format';
import {priceChange} from '../../utils/finance';

export default function MarketScreen({navigation}) {
  const {theme} = useTheme();
  const {t, language} = useTranslation();

  const loadCatalogue = useCallback(async () => {
    const [commodities, markets] = await Promise.all([
      catalogueApi.commodities(),
      catalogueApi.markets(),
    ]);
    return {
      commodities: Array.isArray(commodities) ? commodities : [],
      markets: Array.isArray(markets) ? markets : [],
    };
  }, []);

  const catalogue = useAsync(loadCatalogue);

  const [commodity, setCommodity] = useState(null);
  const [market, setMarket] = useState(null);

  useEffect(() => {
    if (!catalogue.data) {
      return;
    }
    if (!commodity && catalogue.data.commodities.length > 0) {
      const wheat = catalogue.data.commodities.find(item => item.slug === 'wheat');
      setCommodity(wheat || catalogue.data.commodities[0]);
    }
    if (!market && catalogue.data.markets.length > 0) {
      const lahore = catalogue.data.markets.find(item => item.slug === 'lahore-sabzi-mandi');
      setMarket(lahore || catalogue.data.markets[0]);
    }
  }, [catalogue.data, commodity, market]);

  const loadPrices = useCallback(async () => {
    if (!commodity || !market) {
      return null;
    }
    // allSettled: the comparison needs a longer history than the chart, and a
    // forecast outage must not hide today's prices.
    const [history, comparison, forecast] = await Promise.allSettled([
      marketApi.history(commodity.slug, market.slug, 90),
      marketApi.compare(commodity.slug, {days: 7}),
      forecastApi.get(commodity.slug, market.slug, 7),
    ]);
    return {
      history: history.status === 'fulfilled' ? history.value : null,
      comparison: comparison.status === 'fulfilled' ? comparison.value : null,
      forecast: forecast.status === 'fulfilled' ? forecast.value : null,
    };
  }, [commodity, market]);

  const prices = useAsync(loadPrices, {
    immediate: Boolean(commodity && market),
    deps: [commodity && commodity.slug, market && market.slug],
  });

  const series = useMemo(() => {
    const points = (prices.data && prices.data.history && prices.data.history.points) || [];
    return points.map(point => ({
      date: point.price_date,
      value: toNumber(point.avg_price_pkr),
    }));
  }, [prices.data]);

  const change = useMemo(() => priceChange(series.map(point => point.value)), [series]);
  const latest = series.length > 0 ? series[series.length - 1] : null;
  const isSynthetic =
    Boolean(
      prices.data &&
        prices.data.history &&
        (prices.data.history.points || []).some(point => point.source === 'synthetic_fixture'),
    );

  const comparison = prices.data && prices.data.comparison;
  const comparisonRows = useMemo(() => {
    const rows = (comparison && comparison.rows) || [];
    return [...rows].sort(
      (a, b) => (toNumber(b.latest_price_pkr) || 0) - (toNumber(a.latest_price_pkr) || 0),
    );
  }, [comparison]);

  if (catalogue.loading && !catalogue.data) {
    return (
      <Screen>
        <LoadingState />
      </Screen>
    );
  }

  if (catalogue.error && !catalogue.data) {
    return (
      <Screen>
        <ErrorState message={t(catalogue.error.messageKey)} onRetry={catalogue.run} />
      </Screen>
    );
  }

  return (
    <Screen>
      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={
          <RefreshControl
            refreshing={prices.loading}
            onRefresh={() => {
              catalogue.run();
              prices.run();
            }}
          />
        }>
        <Card>
          <AppText variant="caption" color={theme.colors.textMuted} style={styles.label}>
            {t('market.selectCommodity')}
          </AppText>
          <View style={styles.chips}>
            {((catalogue.data && catalogue.data.commodities) || []).map(item => (
              <Button
                key={item.slug}
                testID={`commodity-${item.slug}`}
                title={commodityName(item, language)}
                variant={commodity && commodity.slug === item.slug ? 'primary' : 'secondary'}
                onPress={() => setCommodity(item)}
                style={styles.chip}
              />
            ))}
          </View>

          <AppText variant="caption" color={theme.colors.textMuted} style={styles.label}>
            {t('market.selectMarket')}
          </AppText>
          <View style={styles.chips}>
            {((catalogue.data && catalogue.data.markets) || []).map(item => (
              <Button
                key={item.slug}
                testID={`market-${item.slug}`}
                title={item.name}
                variant={market && market.slug === item.slug ? 'primary' : 'secondary'}
                onPress={() => setMarket(item)}
                style={styles.chip}
              />
            ))}
          </View>
        </Card>

        {isSynthetic ? (
          <View
            style={[
              styles.warning,
              {backgroundColor: theme.colors.surfaceAlt, borderColor: theme.colors.warning},
            ]}>
            <AppText variant="caption" color={theme.colors.warning} testID="synthetic-warning">
              {t('market.sourceWarning')}
            </AppText>
          </View>
        ) : null}

        <Card>
          <View style={styles.headerRow}>
            <AppText variant="h3" style={styles.flex}>
              {t('market.history')}
            </AppText>
            {latest ? <AppText variant="bodyStrong">{formatDate(latest.date)}</AppText> : null}
          </View>

          {prices.loading && !prices.data ? (
            <LoadingState />
          ) : series.length === 0 ? (
            <EmptyState title={t('market.noData')} body={t('market.noDataHint')} />
          ) : (
            <>
              <AppText variant="number" style={styles.latest}>
                {formatPriceWithUnit(latest.value)}
              </AppText>
              {change ? (
                <AppText
                  variant="caption"
                  color={change.percent >= 0 ? theme.colors.profit : theme.colors.loss}>
                  {t('market.change7d')}: {formatPercent(change.percent)} (
                  {formatPrice(change.absolute)})
                </AppText>
              ) : null}
              <PriceChart series={series} width={320} />
              <AppText variant="tiny" color={theme.colors.textMuted} style={styles.unit}>
                {t('market.unit')} · {t('market.observations', {count: series.length})}
              </AppText>
            </>
          )}
        </Card>

        <Card>
          <AppText variant="h3">{t('market.compare')}</AppText>
          {comparisonRows.length === 0 ? (
            <AppText variant="caption" color={theme.colors.textMuted} style={styles.empty}>
              {t('market.noData')}
            </AppText>
          ) : (
            comparisonRows.map((row, index) => (
              <View key={row.market.id} style={styles.compareRow}>
                <View style={styles.flex}>
                  <AppText variant="bodyStrong">{row.market.name}</AppText>
                  {comparison && comparison.best_market_slug === row.market.slug ? (
                    <Badge label={t('market.bestMarket')} tone="success" />
                  ) : null}
                </View>
                <View style={styles.alignEnd}>
                  <AppText variant="bodyStrong">{formatPrice(row.latest_price_pkr)}</AppText>
                  {row.change_pct_7d !== null && row.change_pct_7d !== undefined ? (
                    <AppText
                      variant="tiny"
                      color={
                        (toNumber(row.change_pct_7d) || 0) >= 0
                          ? theme.colors.profit
                          : theme.colors.loss
                      }>
                      {formatPercent(toNumber(row.change_pct_7d))}
                    </AppText>
                  ) : null}
                </View>
              </View>
            ))
          )}
        </Card>

        <Button
          testID="market-forecast"
          title={t('forecast.title')}
          onPress={() =>
            navigation.navigate('Forecast', {
              commoditySlug: commodity && commodity.slug,
              marketSlug: market && market.slug,
              commodityLabel: commodityName(commodity, language),
              marketLabel: market && market.name,
            })
          }
          disabled={!commodity || !market}
        />
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: {padding: 16, paddingBottom: 40},
  label: {marginBottom: 8},
  chips: {flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 12},
  chip: {minHeight: 36, paddingHorizontal: 12},
  warning: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 8,
    padding: 12,
    marginBottom: 12,
  },
  headerRow: {flexDirection: 'row', alignItems: 'center', marginBottom: 8},
  flex: {flex: 1},
  alignEnd: {alignItems: 'flex-end'},
  latest: {marginBottom: 2},
  unit: {marginTop: 6},
  empty: {paddingVertical: 12},
  compareRow: {flexDirection: 'row', alignItems: 'center', paddingVertical: 10, gap: 8},
});
