import React, {useCallback, useMemo, useState} from 'react';
import {RefreshControl, ScrollView, StyleSheet, View} from 'react-native';

import {
  AppText,
  Button,
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  Row,
  Screen,
} from '../components/ui';
import {useTheme} from '../context/ThemeContext';
import {useTranslation} from '../context/LocalizationContext';
import {useAsync} from '../hooks/useAsync';
import {farmApi, weatherApi} from '../services/api';
import {formatDate, toNumber} from '../utils/format';

/**
 * Weather for a farm.
 *
 * WeatherBundle: {current, forecast[], provider, is_live}. A farm without
 * coordinates cannot have weather, and `provider: "mock"` is clearly labelled —
 * showing fabricated-looking numbers as if they were live would be misleading.
 */
export default function WeatherScreen({navigation}) {
  const {theme} = useTheme();
  const {t} = useTranslation();
  const [farmId, setFarmId] = useState(null);

  const load = useCallback(async () => {
    const farms = await farmApi.list();
    const selected =
      farms.find(farm => farm.id === farmId) ||
      farms.find(farm => farm.latitude !== null && farm.latitude !== undefined) ||
      farms[0] ||
      null;
    if (!selected) {
      return {farms, farm: null, weather: null};
    }
    let weather = null;
    try {
      weather = await weatherApi.forFarm(selected.id);
    } catch {
      weather = null;
    }
    return {farms, farm: selected, weather};
  }, [farmId]);

  const {data, error, loading, run} = useAsync(load);

  const forecastDays = useMemo(() => (data && data.weather ? data.weather.forecast || [] : []), [data]);

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

  const farms = (data && data.farms) || [];

  if (farms.length === 0) {
    return (
      <Screen>
        <EmptyState
          title={t('dashboard.noFarmTitle')}
          body={t('dashboard.noFarmBody')}
          actionLabel={t('common.add')}
          onAction={() => navigation.navigate('FarmForm')}
        />
      </Screen>
    );
  }

  const farm = data.farm;
  const weather = data.weather;
  const current = weather && weather.current;
  const isMock = Boolean(weather && (weather.provider === 'mock' || weather.is_live === false));

  return (
    <Screen>
      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={run} />}>
        <Card>
          <AppText variant="caption" color={theme.colors.textMuted} style={styles.label}>
            {t('crops.farm')}
          </AppText>
          <View style={styles.chips}>
            {farms.map(item => (
              <Button
                key={item.id}
                testID={`weather-farm-${item.id}`}
                title={item.name}
                variant={farm && farm.id === item.id ? 'primary' : 'secondary'}
                onPress={() => setFarmId(item.id)}
                style={styles.chip}
              />
            ))}
          </View>
        </Card>

        {!weather ? (
          <Card>
            <AppText variant="caption" color={theme.colors.warning} testID="weather-unavailable">
              {farm && (farm.latitude === null || farm.latitude === undefined)
                ? t('weather.addCoordinates')
                : t('weather.unavailable')}
            </AppText>
            <Button
              title={t('common.edit')}
              variant="secondary"
              style={styles.action}
              onPress={() => navigation.navigate('FarmForm', {mode: 'edit', farmId: farm.id})}
            />
          </Card>
        ) : (
          <>
            {isMock ? (
              <View
                style={[
                  styles.warning,
                  {backgroundColor: theme.colors.surfaceAlt, borderColor: theme.colors.warning},
                ]}>
                <AppText variant="caption" color={theme.colors.warning} testID="weather-mock">
                  {t('weather.simulated')}
                </AppText>
              </View>
            ) : null}

            <Card>
              <AppText variant="h3">{t('weather.current')}</AppText>
              <AppText variant="number" style={styles.temp}>
                {Math.round(toNumber(current && current.temperature_c) ?? 0)}°C
              </AppText>
              <Row
                label={t('weather.humidity')}
                value={`${Math.round(toNumber(current && current.humidity_pct) ?? 0)}%`}
              />
              <Row
                label={t('weather.wind')}
                value={`${(toNumber(current && current.wind_kph) ?? 0).toFixed(0)} km/h`}
              />
              <Row
                label={t('weather.rain')}
                value={`${(toNumber(current && current.precipitation_mm) ?? 0).toFixed(1)} mm`}
              />
              {current && current.condition ? (
                <Row label={t('weather.current')} value={current.condition} />
              ) : null}
              {weather.provider ? (
                <AppText variant="tiny" color={theme.colors.textMuted} style={styles.provider}>
                  {t('weather.provider', {provider: weather.provider})}
                </AppText>
              ) : null}
            </Card>

            {forecastDays.length > 0 ? (
              <Card>
                <AppText variant="h3">{t('weather.forecast7')}</AppText>
                {forecastDays.slice(0, 7).map((day, index) => (
                  <Row
                    key={day.day || index}
                    label={formatDate(day.day)}
                    value={`${Math.round(toNumber(day.temp_max_c) ?? 0)}° / ${Math.round(
                      toNumber(day.temp_min_c) ?? 0,
                    )}°  ·  ${(toNumber(day.precipitation_mm) ?? 0).toFixed(1)} mm`}
                  />
                ))}
              </Card>
            ) : null}
          </>
        )}
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: {padding: 16, paddingBottom: 40},
  label: {marginBottom: 8},
  chips: {flexDirection: 'row', flexWrap: 'wrap', gap: 8},
  chip: {minHeight: 36, paddingHorizontal: 12},
  warning: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 8,
    padding: 12,
    marginBottom: 12,
  },
  temp: {marginVertical: 8},
  provider: {marginTop: 8},
  action: {marginTop: 12},
});
