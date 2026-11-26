/**
 * Navigation tree.
 *
 *   not authenticated -> AuthStack (Welcome, Login, Register)
 *   authenticated     -> MainTabs (Dashboard, Crops, Market, Finance, More)
 *                        with a shared native stack for detail/edit screens
 *
 * The tab bar uses a stacked navigator rather than nested ones so that, for
 * example, "Add expense" can be opened from both Crops and Dashboard.
 */

import React from 'react';
import {ActivityIndicator, StyleSheet, View} from 'react-native';
import {DarkTheme, DefaultTheme, NavigationContainer} from '@react-navigation/native';
import {createNativeStackNavigator} from '@react-navigation/native-stack';
import {createBottomTabNavigator} from '@react-navigation/bottom-tabs';

import {useAuth} from '../context/AuthContext';
import {useTheme} from '../context/ThemeContext';
import {useTranslation} from '../context/LocalizationContext';

import LoginScreen from '../screens/auth/LoginScreen';
import RegisterScreen from '../screens/auth/RegisterScreen';
import WelcomeScreen from '../screens/auth/WelcomeScreen';
import DashboardScreen from '../screens/DashboardScreen';
import CropListScreen from '../screens/crops/CropListScreen';
import CropFormScreen from '../screens/crops/CropFormScreen';
import CropDetailScreen from '../screens/crops/CropDetailScreen';
import ExpenseFormScreen from '../screens/crops/ExpenseFormScreen';
import SaleFormScreen from '../screens/crops/SaleFormScreen';
import MarketScreen from '../screens/market/MarketScreen';
import ForecastScreen from '../screens/market/ForecastScreen';
import FinanceScreen from '../screens/FinanceScreen';
import MoreScreen from '../screens/MoreScreen';
import FarmFormScreen from '../screens/FarmFormScreen';
import WeatherScreen from '../screens/WeatherScreen';
import BuyersScreen from '../screens/BuyersScreen';
import ReportsScreen from '../screens/ReportsScreen';
import SettingsScreen from '../screens/SettingsScreen';

const AuthStack = createNativeStackNavigator();
const RootStack = createNativeStackNavigator();
const Tab = createBottomTabNavigator();

function MainTabs() {
  const {theme} = useTheme();
  const {t} = useTranslation();

  return (
    <Tab.Navigator
      screenOptions={{
        headerStyle: {backgroundColor: theme.colors.surface},
        headerTitleStyle: {color: theme.colors.text},
        headerShadowVisible: false,
        tabBarActiveTintColor: theme.colors.primary,
        tabBarInactiveTintColor: theme.colors.textMuted,
        tabBarStyle: {
          backgroundColor: theme.colors.surface,
          borderTopColor: theme.colors.border,
        },
        tabBarLabelStyle: {fontSize: 11},
      }}>
      <Tab.Screen
        name="DashboardTab"
        component={DashboardScreen}
        options={{title: t('nav.dashboard'), headerTitle: t('nav.dashboard')}}
      />
      <Tab.Screen
        name="CropsTab"
        component={CropListScreen}
        options={{title: t('nav.crops'), headerTitle: t('nav.crops')}}
      />
      <Tab.Screen
        name="MarketTab"
        component={MarketScreen}
        options={{title: t('nav.market'), headerTitle: t('nav.market')}}
      />
      <Tab.Screen
        name="FinanceTab"
        component={FinanceScreen}
        options={{title: t('nav.finance'), headerTitle: t('nav.finance')}}
      />
      <Tab.Screen
        name="MoreTab"
        component={MoreScreen}
        options={{title: t('nav.more'), headerTitle: t('nav.more')}}
      />
    </Tab.Navigator>
  );
}

export default function RootNavigator() {
  const {status} = useAuth();
  const {theme, isDark} = useTheme();
  const {t} = useTranslation();

  const navigationTheme = {
    ...(isDark ? DarkTheme : DefaultTheme),
    colors: {
      ...(isDark ? DarkTheme : DefaultTheme).colors,
      background: theme.colors.background,
      card: theme.colors.surface,
      text: theme.colors.text,
      border: theme.colors.border,
      primary: theme.colors.primary,
    },
  };

  if (status === 'restoring') {
    return (
      <View style={[styles.loadingScreen, {backgroundColor: theme.colors.background}]}>
        <ActivityIndicator size="large" color={theme.colors.primary} />
      </View>
    );
  }

  return (
    <NavigationContainer theme={navigationTheme}>
      {status === 'authenticated' ? (
        <RootStack.Navigator
          screenOptions={{
            headerStyle: {backgroundColor: theme.colors.surface},
            headerTitleStyle: {color: theme.colors.text},
            headerTintColor: theme.colors.primary,
            headerShadowVisible: false,
            contentStyle: {backgroundColor: theme.colors.background},
          }}>
          <RootStack.Screen
            name="Main"
            component={MainTabs}
            options={{headerShown: false}}
          />
          <RootStack.Screen
            name="CropForm"
            component={CropFormScreen}
            options={{title: t('crops.addTitle')}}
          />
          <RootStack.Screen
            name="CropDetail"
            component={CropDetailScreen}
            options={{title: t('crops.detailTitle')}}
          />
          <RootStack.Screen
            name="ExpenseForm"
            component={ExpenseFormScreen}
            options={{title: t('expenses.addTitle')}}
          />
          <RootStack.Screen
            name="SaleForm"
            component={SaleFormScreen}
            options={{title: t('sales.addTitle')}}
          />
          <RootStack.Screen
            name="Forecast"
            component={ForecastScreen}
            options={{title: t('forecast.title')}}
          />
          <RootStack.Screen
            name="FarmForm"
            component={FarmFormScreen}
            options={{title: t('crops.farm')}}
          />
          <RootStack.Screen
            name="Weather"
            component={WeatherScreen}
            options={{title: t('weather.title')}}
          />
          <RootStack.Screen
            name="Buyers"
            component={BuyersScreen}
            options={{title: t('buyers.title')}}
          />
          <RootStack.Screen
            name="Reports"
            component={ReportsScreen}
            options={{title: t('reports.title')}}
          />
          <RootStack.Screen
            name="Settings"
            component={SettingsScreen}
            options={{title: t('settings.title')}}
          />
        </RootStack.Navigator>
      ) : (
        <AuthStack.Navigator
          screenOptions={{
            headerShown: false,
            contentStyle: {backgroundColor: theme.colors.background},
          }}>
          <AuthStack.Screen name="Welcome" component={WelcomeScreen} />
          <AuthStack.Screen name="Login" component={LoginScreen} />
          <AuthStack.Screen name="Register" component={RegisterScreen} />
        </AuthStack.Navigator>
      )}
    </NavigationContainer>
  );
}

const styles = StyleSheet.create({
  loadingScreen: {flex: 1, alignItems: 'center', justifyContent: 'center'},
});
