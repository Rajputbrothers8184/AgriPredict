module.exports = {
  root: true,
  extends: '@react-native',
  env: {jest: true},
  ignorePatterns: ['node_modules/', 'android/', 'ios/', 'coverage/'],
  rules: {
    'react-native/no-inline-styles': 'warn',
    'react-hooks/exhaustive-deps': 'warn',
  },
};
