/**
 * Metro configuration (Community CLI defaults + node_modules asset support).
 * https://reactnative.dev/docs/metro
 */
const {getDefaultConfig, mergeConfig} = require('@react-native/metro-config');

/**
 * https://github.com/facebook/metro/blob/main/docs/Configuration.md
 */
const config = {};

module.exports = mergeConfig(getDefaultConfig(__dirname), config);
