import React, {useCallback, useState} from 'react';
import {Linking, RefreshControl, ScrollView, StyleSheet, View} from 'react-native';

import {
  AppText,
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  Screen,
} from '../components/ui';
import {useTheme} from '../context/ThemeContext';
import {useTranslation} from '../context/LocalizationContext';
import {useAsync} from '../hooks/useAsync';
import {buyerApi} from '../services/api';
import {BUYER_CATEGORIES, labelKeyFor} from '../constants/options';
import {mapApiError} from '../utils/errors';
import {toNumber} from '../utils/format';

/**
 * Nearby buyers.
 *
 * Two different response shapes are involved: `/buyers` returns
 * BuyerSearchResponse {results[], count, source, note} while `/buyers/saved`
 * returns a bare BuyerRead[]. The `source` field distinguishes a live Google
 * Places result from cache and from "unavailable" (no API key configured), and
 * the screen says which it is showing.
 */
export default function BuyersScreen() {
  const {theme} = useTheme();
  const {t} = useTranslation();
  const [savedOnly, setSavedOnly] = useState(false);

  const load = useCallback(async () => {
    const [live, saved] = await Promise.allSettled([buyerApi.search({limit: 20}), buyerApi.saved(50)]);
    return {
      live: live.status === 'fulfilled' ? live.value : null,
      saved: saved.status === 'fulfilled' ? saved.value : [],
      liveError: live.status === 'rejected' ? mapApiError(live.reason) : null,
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

  const live = data && data.live;
  const saved = (data && data.saved) || [];
  const liveResults = live ? live.results || [] : [];
  const rows = savedOnly ? saved : liveResults.length > 0 ? liveResults : saved;
  const unavailable = Boolean(data && data.liveError) || (live && live.source === 'unavailable');
  const showingCache = Boolean(live && live.source === 'cache');

  return (
    <Screen>
      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={run} />}>
        <View style={styles.toggle}>
          <Button
            testID="buyers-live"
            title={t('buyers.search')}
            variant={savedOnly ? 'secondary' : 'primary'}
            onPress={() => setSavedOnly(false)}
            style={styles.toggleButton}
          />
          <Button
            testID="buyers-saved"
            title={t('buyers.cached')}
            variant={savedOnly ? 'primary' : 'secondary'}
            onPress={() => setSavedOnly(true)}
            style={styles.toggleButton}
          />
        </View>

        {unavailable ? (
          <View
            style={[
              styles.banner,
              {backgroundColor: theme.colors.surfaceAlt, borderColor: theme.colors.info},
            ]}>
            <AppText variant="caption" color={theme.colors.info} testID="buyers-not-configured">
              {t('buyers.emptyHint')}
            </AppText>
          </View>
        ) : null}

        {rows.length === 0 ? (
          <EmptyState testID="buyers-empty" title={t('buyers.empty')} body={t('buyers.emptyHint')} />
        ) : (
          rows.map(buyer => (
            <Card key={buyer.id || buyer.place_id} testID={`buyer-${buyer.id || buyer.place_id}`}>
              <View style={styles.header}>
                <AppText variant="h3" style={styles.flex}>
                  {buyer.name}
                </AppText>
                <Badge
                  label={t(labelKeyFor(BUYER_CATEGORIES, buyer.category, 'buyers.categoryOther'))}
                  tone="neutral"
                />
              </View>
              {buyer.address ? (
                <AppText variant="caption" color={theme.colors.textMuted}>
                  {buyer.address}
                </AppText>
              ) : null}
              {buyer.distance_km !== null && buyer.distance_km !== undefined ? (
                <AppText variant="tiny" color={theme.colors.textMuted} style={styles.distance}>
                  {t('buyers.distance', {km: (toNumber(buyer.distance_km) ?? 0).toFixed(1)})}
                </AppText>
              ) : null}
              {buyer.phone ? (
                <Button
                  title={`${t('buyers.call')} ${buyer.phone}`}
                  variant="secondary"
                  style={styles.call}
                  onPress={() => Linking.openURL(`tel:${buyer.phone}`)}
                />
              ) : null}
            </Card>
          ))
        )}

        {showingCache ? (
          <AppText variant="tiny" color={theme.colors.textMuted} style={styles.note}>
            {t('buyers.cached')}
          </AppText>
        ) : null}
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: {padding: 16, paddingBottom: 40},
  toggle: {flexDirection: 'row', gap: 8, marginBottom: 12},
  toggleButton: {flex: 1},
  banner: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 8,
    padding: 12,
    marginBottom: 12,
  },
  header: {flexDirection: 'row', alignItems: 'center', gap: 8},
  flex: {flex: 1},
  distance: {marginTop: 4},
  call: {marginTop: 10, minHeight: 38},
  note: {marginTop: 8, textAlign: 'center'},
});
