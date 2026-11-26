import React, {useCallback, useMemo, useState} from 'react';
import {FlatList, StyleSheet, View} from 'react-native';

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
import {useTheme} from '../../context/ThemeContext';
import {useTranslation} from '../../context/LocalizationContext';
import {useAsync} from '../../hooks/useAsync';
import {commodityName, cropApi, farmApi} from '../../services/api';
import {CROP_STATUSES, labelKeyFor, toneForStatus} from '../../constants/options';
import {formatArea, formatDate, formatPriceWithUnit} from '../../utils/format';
import {profitSummary} from '../../utils/finance';

const FILTERS = ['all', 'active', 'harvested'];

export default function CropListScreen({navigation}) {
  const {theme} = useTheme();
  const {t, language} = useTranslation();
  const [filter, setFilter] = useState('all');

  const load = useCallback(async () => {
    const [cycles, farms] = await Promise.all([cropApi.list(), farmApi.list()]);
    return {cycles: Array.isArray(cycles) ? cycles : [], farms};
  }, []);

  const {data, error, loading, run} = useAsync(load);

  const visible = useMemo(() => {
    const cycles = (data && data.cycles) || [];
    return filter === 'all' ? cycles : cycles.filter(cycle => cycle.status === filter);
  }, [data, filter]);

  const farmName = useCallback(
    farmId => {
      const match = ((data && data.farms) || []).find(farm => farm.id === farmId);
      return match ? match.name : '';
    },
    [data],
  );

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

  return (
    <Screen>
      <View style={styles.filters}>
        {FILTERS.map(option => {
          const label =
            option === 'all'
              ? t('common.all')
              : t(
                  labelKeyFor(
                    CROP_STATUSES,
                    option,
                    option === 'active' ? 'crops.statusActive' : 'crops.statusHarvested',
                  ),
                );
          return (
            <Button
              key={option}
              testID={`crop-filter-${option}`}
              title={label}
              variant={filter === option ? 'primary' : 'secondary'}
              onPress={() => setFilter(option)}
              style={styles.filterButton}
            />
          );
        })}
      </View>

      <FlatList
        data={visible}
        keyExtractor={item => String(item.id)}
        contentContainerStyle={styles.list}
        refreshing={loading}
        onRefresh={run}
        ListEmptyComponent={
          <EmptyState
            testID="crops-empty"
            title={t('crops.empty')}
            body={t('crops.emptyHint')}
            actionLabel={t('dashboard.addCrop')}
            onAction={() =>
              navigation.navigate('CropForm', {
                mode: 'create',
                farms: (data && data.farms) || [],
              })
            }
          />
        }
        renderItem={({item}) => {
          // The list endpoint returns CropCycleRead without expenses/sales, so
          // cost and revenue are only shown once known (detail screen).
          const summary = profitSummary({
            expenses: item.expenses || [],
            sales: item.sales || [],
          });
          return (
            <Card testID={`crop-card-${item.id}`}>
              <View style={styles.cardTop}>
                <AppText variant="h3" style={styles.flex}>
                  {commodityName(item.commodity, language)}
                </AppText>
                <Badge
                  label={t(labelKeyFor(CROP_STATUSES, item.status, 'crops.statusActive'))}
                  tone={toneForStatus(item.status)}
                />
              </View>

              <AppText variant="caption" color={theme.colors.textMuted} style={styles.meta}>
                {farmName(item.farm_id)} · {formatArea(item.area_acres)} ·{' '}
                {formatDate(item.sowing_date)}
              </AppText>

              {summary.cost > 0 ? (
                <AppText variant="caption" color={theme.colors.textMuted} style={styles.metrics}>
                  {t('crops.profit')}:{' '}
                  <AppText
                    variant="bodyStrong"
                    color={summary.isProfit ? theme.colors.profit : theme.colors.loss}>
                    {formatPriceWithUnit(summary.profit)}
                  </AppText>
                </AppText>
              ) : null}

              <Button
                title={t('common.viewAll')}
                variant="ghost"
                onPress={() => navigation.navigate('CropDetail', {cropId: item.id})}
                style={styles.detailButton}
              />
            </Card>
          );
        }}
      />

      <View style={styles.footer}>
        <Button
          testID="crops-add"
          title={t('dashboard.addCrop')}
          onPress={() =>
            navigation.navigate('CropForm', {
              mode: 'create',
              farms: (data && data.farms) || [],
            })
          }
        />
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  filters: {flexDirection: 'row', gap: 8, padding: 16, paddingBottom: 8},
  filterButton: {flex: 1, minHeight: 38, paddingHorizontal: 8},
  list: {padding: 16, paddingTop: 4, paddingBottom: 96},
  cardTop: {flexDirection: 'row', alignItems: 'center', gap: 8},
  flex: {flex: 1},
  meta: {marginTop: 4},
  metrics: {marginTop: 8},
  detailButton: {marginTop: 6, minHeight: 38, alignSelf: 'flex-start', paddingHorizontal: 0},
  footer: {padding: 16},
});
