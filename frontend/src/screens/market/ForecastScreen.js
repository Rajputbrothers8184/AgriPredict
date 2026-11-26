import React, {useCallback, useMemo, useState} from 'react';
import {RefreshControl, ScrollView, StyleSheet, View} from 'react-native';

import {
  AppText,
  Badge,
  Button,
  Card,
  ErrorState,
  LoadingState,
  Row,
  Screen,
} from '../../components/ui';
import PriceChart from '../../components/PriceChart';
import {useTheme} from '../../context/ThemeContext';
import {useTranslation} from '../../context/LocalizationContext';
import {useAsync} from '../../hooks/useAsync';
import {forecastApi, marketApi} from '../../services/api';
import {FORECAST_HORIZONS} from '../../constants/options';
import {formatDate, formatPercent, formatPriceWithUnit, toNumber} from '../../utils/format';

/**
 * Forecast screen.
 *
 * Honesty rules enforced here:
 *  - the model's backtested MAE is shown beside the numbers, not buried;
 *  - when the API reports `is_fallback`, a badge explains that a simpler
 *    estimate is being served;
 *  - the confidence band comes from `lower_bound_pkr`/`upper_bound_pkr`, which
 *    the ML service derives from measured error — never invented in the UI;
 *  - the server's own disclaimer is displayed verbatim.
 */
export default function ForecastScreen({navigation, route}) {
  const {theme} = useTheme();
  const {t} = useTranslation();
  const params = route.params || {};
  const [horizon, setHorizon] = useState(7);

  const load = useCallback(async () => {
    const [forecast, history] = await Promise.all([
      forecastApi.get(params.commoditySlug, params.marketSlug, horizon),
      marketApi.history(params.commoditySlug, params.marketSlug, 30),
    ]);
    return {forecast, history};
  }, [params.commoditySlug, params.marketSlug, horizon]);

  const {data, error, loading, run} = useAsync(load, {
    deps: [params.commoditySlug, params.marketSlug, horizon],
  });

  const series = useMemo(() => {
    const points = (data && data.history && data.history.points) || [];
    return points.map(point => ({
      date: point.price_date,
      value: toNumber(point.avg_price_pkr),
    }));
  }, [data]);

  const predictions = useMemo(() => {
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

  const forecast = (data && data.forecast) || {};
  const first = predictions[0];
  const lastHistory = series.length > 0 ? series[series.length - 1].value : null;
  const firstChange =
    first && lastHistory ? ((first.value - lastHistory) / lastHistory) * 100 : null;
  const direction =
    firstChange === null
      ? null
      : firstChange > 1
        ? t('forecast.directionRise')
        : firstChange < -1
          ? t('forecast.directionFall')
          : t('forecast.directionHold');

  const modelName = forecast.model_name || null;
  const mae = toNumber(forecast.mae);
  const rmse = toNumber(forecast.rmse);

  return (
    <Screen>
      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={run} />}>
        <Card>
          <AppText variant="h2">{params.commodityLabel || params.commoditySlug}</AppText>
          <AppText variant="caption" color={theme.colors.textMuted}>
            {params.marketLabel || params.marketSlug}
          </AppText>

          <View style={styles.horizonRow}>
            {FORECAST_HORIZONS.map(option => (
              <Button
                key={option.value}
                testID={`horizon-${option.value}`}
                title={t(option.labelKey)}
                variant={horizon === option.value ? 'primary' : 'secondary'}
                onPress={() => setHorizon(option.value)}
                style={styles.horizonButton}
              />
            ))}
          </View>
        </Card>

        {forecast.is_fallback ? (
          <Card style={{borderColor: theme.colors.warning}}>
            <Badge label={t('forecast.fallbackBadge')} tone="warning" />
            <AppText variant="caption" color={theme.colors.textMuted} style={styles.note}>
              {t('forecast.fallbackNote')}
            </AppText>
          </Card>
        ) : null}

        <Card>
          <AppText variant="h3">{t('forecast.title')}</AppText>
          {predictions.length === 0 ? (
            <AppText variant="caption" color={theme.colors.textMuted} style={styles.empty}>
              {t('forecast.insufficientHistory')}
            </AppText>
          ) : (
            <>
              <AppText variant="number" style={styles.headline}>
                {formatPriceWithUnit(first.value)}
              </AppText>
              <AppText variant="tiny" color={theme.colors.textMuted}>
                {formatDate(first.date)}
                {firstChange !== null
                  ? ` · ${t('forecast.expectedChange', {
                      direction,
                      percent: formatPercent(Math.abs(firstChange)),
                    })}`
                  : ''}
              </AppText>

              <PriceChart series={series} forecast={predictions} width={320} showBand />
            </>
          )}
        </Card>

        <Card>
          <AppText variant="h3">{t('forecast.model')}</AppText>
          <Row label={t('forecast.model')} value={modelName || '—'} />
          <Row
            label={t('forecast.accuracy')}
            value={mae === null ? t('forecast.accuracyUnavailable') : formatPriceWithUnit(mae)}
          />
          {rmse !== null ? <Row label="RMSE" value={formatPriceWithUnit(rmse)} /> : null}
          {horizon === 30 ? (
            <AppText variant="tiny" color={theme.colors.textMuted} style={styles.note}>
              30-day forecasts carry materially more error than 7-day ones. Treat the outer
              band as the plausible range.
            </AppText>
          ) : null}
        </Card>

        <Card>
          <AppText variant="h3">{`${t('forecast.horizon7')} / ${t('forecast.horizon30')}`}</AppText>
          {predictions.map(point => (
            <Row
              key={point.date}
              label={formatDate(point.date)}
              value={`${formatPriceWithUnit(point.value)}  (${formatPriceWithUnit(
                point.lower,
              )}–${formatPriceWithUnit(point.upper)})`}
            />
          ))}
        </Card>

        <AppText variant="tiny" color={theme.colors.textMuted} style={styles.disclaimer}>
          {forecast.disclaimer || t('forecast.disclaimer')}
        </AppText>
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: {padding: 16, paddingBottom: 40},
  horizonRow: {flexDirection: 'row', gap: 8, marginTop: 12},
  horizonButton: {flex: 1},
  note: {marginTop: 8},
  headline: {marginTop: 8},
  empty: {paddingVertical: 12},
  disclaimer: {paddingHorizontal: 4},
});
