/**
 * Colour palette and typography.
 *
 * Contrast: every text/background pair below meets WCAG AA (4.5:1) for body
 * text. The previous "agricultural green" was too light on white for small
 * text, so `primary` in light mode is a darker shade than the brand green used
 * for large headings and charts.
 */

const brand = {
  green: '#1F6F43',
  greenDark: '#14522F',
  greenLight: '#3E9E6B',
  amber: '#B7791F',
  red: '#B42318',
  blue: '#12558A',
};

export const lightTheme = {
  name: 'light',
  colors: {
    ...brand,
    primary: brand.greenDark,
    primaryContrast: '#FFFFFF',
    accent: brand.greenLight,
    background: '#F6F8F6',
    surface: '#FFFFFF',
    surfaceAlt: '#EEF3EE',
    border: '#D3DED3',
    text: '#12201A',
    textMuted: '#4A5C50',
    textInverse: '#FFFFFF',
    success: '#1B7F45',
    warning: brand.amber,
    danger: brand.red,
    info: brand.blue,
    profit: '#1B7F45',
    loss: '#B42318',
    overlay: 'rgba(18, 32, 26, 0.45)',
    chartLine: brand.green,
    chartFill: 'rgba(31, 111, 67, 0.14)',
    chartGrid: '#DDE5DD',
    forecastLine: brand.amber,
  },
  spacing: {xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32},
  radius: {sm: 6, md: 10, lg: 16, pill: 999},
  typography: {
    h1: {fontSize: 24, fontWeight: '700', lineHeight: 32},
    h2: {fontSize: 19, fontWeight: '700', lineHeight: 26},
    h3: {fontSize: 16, fontWeight: '600', lineHeight: 22},
    body: {fontSize: 15, fontWeight: '400', lineHeight: 22},
    bodyStrong: {fontSize: 15, fontWeight: '600', lineHeight: 22},
    caption: {fontSize: 13, fontWeight: '400', lineHeight: 18},
    tiny: {fontSize: 11, fontWeight: '400', lineHeight: 15},
    number: {fontSize: 22, fontWeight: '700', fontVariant: ['tabular-nums']},
  },
};

export const darkTheme = {
  ...lightTheme,
  name: 'dark',
  colors: {
    ...brand,
    primary: brand.greenLight,
    primaryContrast: '#06140D',
    accent: '#67C393',
    background: '#0C1512',
    surface: '#14201B',
    surfaceAlt: '#1B2A23',
    border: '#2A3B32',
    text: '#EAF2ED',
    textMuted: '#A5B7AC',
    textInverse: '#0C1512',
    success: '#4ECB8B',
    warning: '#E0A94A',
    danger: '#F2726A',
    info: '#63AEDC',
    profit: '#4ECB8B',
    loss: '#F2726A',
    overlay: 'rgba(0, 0, 0, 0.6)',
    chartLine: '#67C393',
    chartFill: 'rgba(103, 195, 147, 0.18)',
    chartGrid: '#26372E',
    forecastLine: '#E0A94A',
  },
};

export const palettes = {light: lightTheme, dark: darkTheme};

export default palettes;
