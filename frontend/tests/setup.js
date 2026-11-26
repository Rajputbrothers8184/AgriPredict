/* eslint-env jest */

/**
 * Jest setup.
 *
 * Only the native modules that have no JS implementation are mocked. Nothing
 * that carries app logic is stubbed: the services, i18n, validators and finance
 * helpers are exercised for real, so the tests can actually catch regressions.
 */

jest.mock('@react-native-async-storage/async-storage', () =>
  require('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

jest.mock('react-native-safe-area-context', () => {
  const React = require('react');
  const {View} = require('react-native');
  return {
    SafeAreaProvider: ({children}) => React.createElement(View, null, children),
    SafeAreaView: ({children, ...props}) => React.createElement(View, props, children),
    useSafeAreaInsets: () => ({top: 0, right: 0, bottom: 0, left: 0}),
    useSafeAreaFrame: () => ({x: 0, y: 0, width: 390, height: 844}),
  };
});

// react-native-svg renders into native views; a plain View is enough for the
// chart's structural assertions.
jest.mock('react-native-svg', () => {
  const React = require('react');
  const {View, Text} = require('react-native');
  const make = name => {
    const Component = props => React.createElement(View, props, props.children);
    Component.displayName = name;
    return Component;
  };
  return {
    __esModule: true,
    default: make('Svg'),
    Svg: make('Svg'),
    G: make('G'),
    Path: make('Path'),
    Line: make('Line'),
    Circle: make('Circle'),
    Polygon: make('Polygon'),
    Rect: make('Rect'),
    Text: props => React.createElement(Text, props, props.children),
  };
});

global.__DEV__ = true;

// React 18's act() must be told this is an act-aware environment.
global.IS_REACT_ACT_ENVIRONMENT = true;
