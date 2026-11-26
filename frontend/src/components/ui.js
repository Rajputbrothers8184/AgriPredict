/**
 * Small shared UI primitives.
 *
 * Written by hand rather than pulling in a component library: the app needs a
 * handful of accessible components, and native components keep the APK small
 * and the styles fully themeable (including RTL).
 */

import React from 'react';
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import {useTheme} from '../context/ThemeContext';
import {useTranslation} from '../context/LocalizationContext';

// ---------------------------------------------------------------------------
// Text
// ---------------------------------------------------------------------------
export function AppText({variant = 'body', color, style, children, ...rest}) {
  const {theme} = useTheme();
  const {isRtl} = useTranslation();
  const typography = theme.typography[variant] || theme.typography.body;
  return (
    <Text
      {...rest}
      style={[
        typography,
        {color: color || theme.colors.text, textAlign: isRtl ? 'right' : 'left'},
        style,
      ]}>
      {children}
    </Text>
  );
}

// ---------------------------------------------------------------------------
// Screen scaffolding
// ---------------------------------------------------------------------------
export function Screen({children, style}) {
  const {theme} = useTheme();
  return (
    <View style={[styles.screen, {backgroundColor: theme.colors.background}, style]}>
      {children}
    </View>
  );
}

export function Card({children, style, testID}) {
  const {theme} = useTheme();
  return (
    <View
      testID={testID}
      style={[
        styles.card,
        {
          backgroundColor: theme.colors.surface,
          borderColor: theme.colors.border,
          borderRadius: theme.radius.md,
        },
        style,
      ]}>
      {children}
    </View>
  );
}

export function Divider() {
  const {theme} = useTheme();
  return <View style={{height: StyleSheet.hairlineWidth, backgroundColor: theme.colors.border}} />;
}

// ---------------------------------------------------------------------------
// Buttons
// ---------------------------------------------------------------------------
export function Button({
  title,
  onPress,
  variant = 'primary',
  disabled = false,
  loading = false,
  style,
  testID,
}) {
  const {theme} = useTheme();
  const isDisabled = disabled || loading;

  const background = {
    primary: theme.colors.primary,
    secondary: theme.colors.surfaceAlt,
    danger: theme.colors.danger,
    ghost: 'transparent',
  }[variant];

  const textColor = {
    primary: theme.colors.primaryContrast,
    secondary: theme.colors.text,
    danger: '#FFFFFF',
    ghost: theme.colors.primary,
  }[variant];

  return (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      accessibilityState={{disabled: isDisabled, busy: loading}}
      // `disabled` must reach the Pressable, not just accessibilityState:
      // otherwise the pressability handler still fires for a disabled button.
      disabled={isDisabled}
      onPress={onPress}
      style={({pressed}) => [
        styles.button,
        {
          backgroundColor: background,
          borderColor: variant === 'ghost' ? theme.colors.primary : background,
          borderRadius: theme.radius.md,
          opacity: isDisabled ? 0.55 : pressed ? 0.85 : 1,
        },
        style,
      ]}>
      {loading ? (
        <ActivityIndicator color={textColor} />
      ) : (
        <Text style={[styles.buttonLabel, {color: textColor}]}>{title}</Text>
      )}
    </Pressable>
  );
}

// ---------------------------------------------------------------------------
// Form fields
// ---------------------------------------------------------------------------
export function Field({label, error, hint, required = false, children}) {
  const {theme} = useTheme();
  return (
    <View style={styles.field}>
      {label ? (
        <AppText variant="caption" color={theme.colors.textMuted} style={styles.fieldLabel}>
          {label}
          {required ? ' *' : ''}
        </AppText>
      ) : null}
      {children}
      {error ? (
        <AppText variant="tiny" color={theme.colors.danger} style={styles.fieldHint}>
          {error}
        </AppText>
      ) : hint ? (
        <AppText variant="tiny" color={theme.colors.textMuted} style={styles.fieldHint}>
          {hint}
        </AppText>
      ) : null}
    </View>
  );
}

export function Input({label, error, hint, required, style, testID, ...rest}) {
  const {theme} = useTheme();
  const {isRtl} = useTranslation();
  return (
    <Field label={label} error={error} hint={hint} required={required}>
      <TextInput
        testID={testID}
        placeholderTextColor={theme.colors.textMuted}
        style={[
          styles.input,
          {
            backgroundColor: theme.colors.surface,
            borderColor: error ? theme.colors.danger : theme.colors.border,
            borderRadius: theme.radius.sm,
            color: theme.colors.text,
            textAlign: isRtl ? 'right' : 'left',
          },
          style,
        ]}
        accessibilityLabel={label}
        {...rest}
      />
    </Field>
  );
}

// ---------------------------------------------------------------------------
// Feedback
// ---------------------------------------------------------------------------
export function Badge({label, tone = 'neutral'}) {
  const {theme} = useTheme();
  const palette = {
    neutral: theme.colors.surfaceAlt,
    success: theme.colors.success,
    warning: theme.colors.warning,
    danger: theme.colors.danger,
    info: theme.colors.info,
  };
  const background = palette[tone] || palette.neutral;
  const textColor = tone === 'neutral' ? theme.colors.text : '#FFFFFF';
  return (
    <View style={[styles.badge, {backgroundColor: background, borderRadius: theme.radius.pill}]}>
      <Text style={[styles.badgeLabel, {color: textColor}]}>{label}</Text>
    </View>
  );
}

export function LoadingState({label}) {
  const {theme} = useTheme();
  const {t} = useTranslation();
  return (
    <View style={styles.centered}>
      <ActivityIndicator size="large" color={theme.colors.primary} />
      <AppText variant="caption" color={theme.colors.textMuted} style={styles.stateText}>
        {label || t('common.loading')}
      </AppText>
    </View>
  );
}

export function ErrorState({message, onRetry}) {
  const {theme} = useTheme();
  const {t} = useTranslation();
  return (
    <View style={styles.centered}>
      <AppText variant="bodyStrong" color={theme.colors.danger} style={styles.stateText}>
        {message || t('common.somethingWentWrong')}
      </AppText>
      {onRetry ? (
        <Button title={t('common.retry')} variant="secondary" onPress={onRetry} style={styles.retry} />
      ) : null}
    </View>
  );
}

export function EmptyState({title, body, actionLabel, onAction, testID}) {
  const {theme} = useTheme();
  return (
    <View style={styles.centered} testID={testID}>
      <AppText variant="h3" style={styles.stateText}>
        {title}
      </AppText>
      {body ? (
        <AppText variant="caption" color={theme.colors.textMuted} style={styles.stateText}>
          {body}
        </AppText>
      ) : null}
      {actionLabel && onAction ? (
        <Button title={actionLabel} onPress={onAction} style={styles.retry} />
      ) : null}
    </View>
  );
}

// ---------------------------------------------------------------------------
// Data display
// ---------------------------------------------------------------------------
export function StatTile({label, value, hint, tone}) {
  const {theme} = useTheme();
  const valueColor =
    tone === 'profit'
      ? theme.colors.profit
      : tone === 'loss'
        ? theme.colors.loss
        : theme.colors.text;
  return (
    <Card style={styles.stat}>
      <AppText variant="tiny" color={theme.colors.textMuted}>
        {label}
      </AppText>
      <AppText variant="number" color={valueColor} style={styles.statValue}>
        {value}
      </AppText>
      {hint ? (
        <AppText variant="tiny" color={theme.colors.textMuted}>
          {hint}
        </AppText>
      ) : null}
    </Card>
  );
}

export function Row({label, value, strong = false, tone}) {
  const {theme} = useTheme();
  const color =
    tone === 'profit'
      ? theme.colors.profit
      : tone === 'loss'
        ? theme.colors.loss
        : theme.colors.text;
  return (
    <View style={styles.row}>
      <AppText variant={strong ? 'bodyStrong' : 'body'} color={theme.colors.textMuted}>
        {label}
      </AppText>
      <AppText variant={strong ? 'bodyStrong' : 'body'} color={color}>
        {value}
      </AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {flex: 1},
  card: {borderWidth: StyleSheet.hairlineWidth, padding: 14, marginBottom: 12},
  button: {
    minHeight: 46,
    paddingHorizontal: 18,
    borderWidth: StyleSheet.hairlineWidth,
    alignItems: 'center',
    justifyContent: 'center',
  },
  buttonLabel: {fontSize: 15, fontWeight: '600'},
  field: {marginBottom: 14},
  fieldLabel: {marginBottom: 6},
  fieldHint: {marginTop: 4},
  input: {
    minHeight: 46,
    borderWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: 12,
    fontSize: 15,
  },
  badge: {paddingHorizontal: 10, paddingVertical: 3, alignSelf: 'flex-start'},
  badgeLabel: {fontSize: 11, fontWeight: '600'},
  centered: {flex: 1, alignItems: 'center', justifyContent: 'center', padding: 28},
  stateText: {textAlign: 'center', marginTop: 8},
  retry: {marginTop: 16, minWidth: 140},
  stat: {flex: 1, minWidth: 140},
  statValue: {marginVertical: 4},
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 7,
  },
});
