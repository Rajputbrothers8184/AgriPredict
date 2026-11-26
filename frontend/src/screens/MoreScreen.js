import React from 'react';
import {ScrollView, StyleSheet, View} from 'react-native';

import {AppText, Button, Card, Screen} from '../components/ui';
import {useAuth} from '../context/AuthContext';
import {useTheme} from '../context/ThemeContext';
import {useTranslation} from '../context/LocalizationContext';
import {PRICE_UNIT} from '../config';

export default function MoreScreen({navigation}) {
  const {theme} = useTheme();
  const {t} = useTranslation();
  const {user, logout} = useAuth();

  const items = [
    {label: t('weather.title'), route: 'Weather'},
    {label: t('buyers.title'), route: 'Buyers'},
    {label: t('reports.title'), route: 'Reports'},
    {label: t('settings.title'), route: 'Settings'},
  ];

  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.content}>
        <Card>
          <AppText variant="h3">{user && user.full_name ? user.full_name : '—'}</AppText>
          <AppText variant="caption" color={theme.colors.textMuted}>
            {user && user.email ? user.email : ''}
          </AppText>
        </Card>

        <Card>
          {items.map(item => (
            <View key={item.route} style={styles.item}>
              <Button
                testID={`more-${item.route}`}
                title={item.label}
                variant="secondary"
                onPress={() => navigation.navigate(item.route)}
              />
            </View>
          ))}
        </Card>

        <Card>
          <AppText variant="caption" color={theme.colors.textMuted}>
            {t('settings.version')} 0.5.0 · {PRICE_UNIT}
          </AppText>
        </Card>

        <Button
          testID="more-logout"
          title={t('auth.logout')}
          variant="danger"
          onPress={logout}
          style={styles.logout}
        />
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: {padding: 16, paddingBottom: 40},
  item: {marginBottom: 10},
  logout: {marginTop: 8},
});
