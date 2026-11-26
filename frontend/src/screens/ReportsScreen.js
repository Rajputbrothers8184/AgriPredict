import React, {useCallback, useMemo, useState} from 'react';
import {Linking, ScrollView, StyleSheet, View} from 'react-native';

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
import {absoluteDownloadUrl, commodityName, cropApi, reportApi} from '../services/api';
import {mapApiError} from '../utils/errors';
import {formatDateTime} from '../utils/format';

/**
 * Report generation.
 *
 * ReportCreate takes {report_type, file_format, crop_cycle_id}; ReportRead
 * returns `download_url` as a server-relative path with a signed, short-lived
 * token (`/api/v1/reports/3/download?token=…`). Handing that URL to the system
 * browser is therefore safe and needs no header — the signature names the owner
 * and the single report it unlocks.
 */
export default function ReportsScreen({route}) {
  const {theme} = useTheme();
  const {t, language} = useTranslation();
  const preselectedCropId = route.params ? route.params.cropId : null;

  const [cropId, setCropId] = useState(preselectedCropId || 'all');
  const [generating, setGenerating] = useState(null);
  const [notice, setNotice] = useState(null);

  const load = useCallback(async () => {
    const [cycles, reports] = await Promise.allSettled([cropApi.list(), reportApi.list()]);
    return {
      cycles: cycles.status === 'fulfilled' ? cycles.value : [],
      reports: reports.status === 'fulfilled' ? reports.value : [],
    };
  }, []);

  const {data, error: loadError, loading, run} = useAsync(load);

  const cycles = useMemo(() => (data && data.cycles) || [], [data]);
  const reports = (data && data.reports) || [];

  async function generate(format) {
    setGenerating(format);
    setNotice(null);
    try {
      const report = await reportApi.create({
        reportType: cropId === 'all' ? 'financial_summary' : 'crop_cycle',
        fileFormat: format,
        cropCycleId: cropId === 'all' ? null : Number(cropId),
      });

      // The URL carries a short-lived signed token, so the browser/download
      // manager can fetch it without an Authorization header.
      const absolute = absoluteDownloadUrl(report);
      if (!absolute) {
        setNotice('reports.failed');
        return;
      }
      await Linking.openURL(absolute);
      setNotice('reports.generated');
      run();
    } catch (caught) {
      setNotice(mapApiError(caught).messageKey);
    } finally {
      setGenerating(null);
    }
  }

  if (loading && !data) {
    return (
      <Screen>
        <LoadingState />
      </Screen>
    );
  }

  if (loadError && !data) {
    return (
      <Screen>
        <ErrorState message={t(loadError.messageKey)} onRetry={run} />
      </Screen>
    );
  }

  if (cycles.length === 0 && reports.length === 0) {
    return (
      <Screen>
        <EmptyState title={t('crops.empty')} body={t('crops.emptyHint')} />
      </Screen>
    );
  }

  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.content}>
        <Card>
          <AppText variant="h3">{t('reports.title')}</AppText>
          <View style={styles.chips}>
            <Button
              testID="report-scope-all"
              title={t('reports.allCyclesReport')}
              variant={cropId === 'all' ? 'primary' : 'secondary'}
              onPress={() => setCropId('all')}
              style={styles.chip}
            />
            {cycles.map(cycle => (
              <Button
                key={cycle.id}
                testID={`report-scope-${cycle.id}`}
                title={commodityName(cycle.commodity, language)}
                variant={String(cropId) === String(cycle.id) ? 'primary' : 'secondary'}
                onPress={() => setCropId(String(cycle.id))}
                style={styles.chip}
              />
            ))}
          </View>

          {notice ? (
            <AppText
              variant="caption"
              color={
                notice === 'reports.generated' ? theme.colors.success : theme.colors.danger
              }
              testID="report-notice">
              {t(notice)}
            </AppText>
          ) : null}

          <Button
            testID="report-pdf"
            title={t('reports.pdf')}
            onPress={() => generate('pdf')}
            loading={generating === 'pdf'}
            disabled={generating !== null && generating !== 'pdf'}
            style={styles.action}
          />
          <Button
            testID="report-xlsx"
            title={t('reports.excel')}
            variant="secondary"
            onPress={() => generate('xlsx')}
            loading={generating === 'xlsx'}
            disabled={generating !== null && generating !== 'xlsx'}
            style={styles.action}
          />
          {generating ? (
            <AppText variant="tiny" color={theme.colors.textMuted} style={styles.hint}>
              {t('reports.generating')}
            </AppText>
          ) : null}
        </Card>

        <Card>
          <AppText variant="h3">{t('reports.history')}</AppText>
          {reports.length === 0 ? (
            <AppText variant="caption" color={theme.colors.textMuted} style={styles.empty}>
              —
            </AppText>
          ) : (
            reports.map(report => (
              <View key={report.id} style={styles.reportRow}>
                <View style={styles.flex}>
                  <AppText variant="bodyStrong">
                    {(report.file_format || '').toUpperCase()} · {report.filename || report.report_type}
                  </AppText>
                  <AppText variant="tiny" color={theme.colors.textMuted}>
                    {formatDateTime(report.created_at)}
                  </AppText>
                </View>
                {report.expires_at ? (
                  <Badge
                    label={formatDateTime(report.expires_at).split(',')[0]}
                    tone={new Date(report.expires_at) < new Date() ? 'danger' : 'success'}
                  />
                ) : null}
              </View>
            ))
          )}
        </Card>
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: {padding: 16, paddingBottom: 40},
  chips: {flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginVertical: 12},
  chip: {minHeight: 36, paddingHorizontal: 12},
  action: {marginTop: 10},
  hint: {marginTop: 8},
  empty: {paddingVertical: 12},
  flex: {flex: 1},
  reportRow: {flexDirection: 'row', alignItems: 'center', paddingVertical: 10, gap: 8},
});
