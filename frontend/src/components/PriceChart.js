/**
 * Price history line chart, drawn with react-native-svg.
 *
 * Self-contained rather than a charting dependency, for three reasons that
 * generic libraries make awkward: the axis must be able to state the PKR/40kg
 * unit, the forecast segment must be visually distinct (dashed), and the
 * forecast confidence band must be shaded.
 *
 * Points are `{date, value, lower?, upper?}`. Non-numeric values are dropped
 * before scaling so a single null cannot produce NaN coordinates.
 */

import React, {useMemo} from 'react';
import {StyleSheet, View} from 'react-native';
import Svg, {Circle, Path, Polygon, Text as SvgText} from 'react-native-svg';

import {AppText} from './ui';
import {useTheme} from '../context/ThemeContext';
import {formatCompact} from '../utils/format';

const HEIGHT = 190;
const PAD = {top: 12, right: 10, bottom: 22, left: 44};

function isFiniteNumber(value) {
  return typeof value === 'number' && Number.isFinite(value);
}

function buildScales(points, width, height) {
  const values = points.flatMap(point =>
    [point.value, point.lower, point.upper].filter(isFiniteNumber),
  );

  const min = Math.min(...values);
  const max = Math.max(...values);
  // A flat series would divide by zero; give it an artificial band.
  const span = max - min || Math.max(Math.abs(max) * 0.02, 1);
  const low = min - span * 0.08;
  const high = max + span * 0.08;

  const plotWidth = width - PAD.left - PAD.right;
  const plotHeight = height - PAD.top - PAD.bottom;

  return {
    x: index =>
      PAD.left + (points.length <= 1 ? plotWidth / 2 : (index / (points.length - 1)) * plotWidth),
    y: value => PAD.top + plotHeight - ((value - low) / (high - low)) * plotHeight,
    ticks: [high, (high + low) / 2, low],
  };
}

export default function PriceChart({
  series = [],
  forecast = [],
  width = 320,
  height = HEIGHT,
  showBand = true,
}) {
  const {theme} = useTheme();

  const points = useMemo(
    () =>
      [
        ...series.map(item => ({...item, isForecast: false})),
        ...forecast.map(item => ({...item, isForecast: true})),
      ].filter(item => isFiniteNumber(item.value)),
    [series, forecast],
  );

  const {x, y, ticks} = useMemo(
    () => buildScales(points, width, height),
    [points, width, height],
  );

  if (points.length === 0) {
    return (
      <View style={[styles.empty, {height}]}>
        <AppText variant="caption" color={theme.colors.textMuted}>
          —
        </AppText>
      </View>
    );
  }

  const historyCount = points.filter(point => !point.isForecast).length;

  const pathFor = (from, to) =>
    points
      .slice(from, to)
      .map((point, offset) => `${offset === 0 ? 'M' : 'L'}${x(from + offset)},${y(point.value)}`)
      .join(' ');

  const historyPath = historyCount > 0 ? pathFor(0, historyCount) : '';
  // Start the forecast line at the last observed point so there is no visual gap.
  const forecastPath =
    forecast.length > 0 ? pathFor(Math.max(historyCount - 1, 0), points.length) : '';

  const bandPoints = points.filter(point => isFiniteNumber(point.lower) && isFiniteNumber(point.upper));
  const bandPolygon =
    bandPoints.length > 1
      ? [
          ...bandPoints.map(point => `${x(points.indexOf(point))},${y(point.upper)}`),
          ...bandPoints
            .slice()
            .reverse()
            .map(point => `${x(points.indexOf(point))},${y(point.lower)}`),
        ].join(' ')
      : null;

  const areaPolygon =
    historyCount > 0
      ? [
          ...Array.from(
            {length: historyCount},
            (_, index) => `${x(index)},${y(points[index].value)}`,
          ),
          `${x(historyCount - 1)},${height - PAD.bottom}`,
          `${x(0)},${height - PAD.bottom}`,
        ].join(' ')
      : null;

  const firstDate = String(points[0].date || '').slice(5);
  const lastPoint = points[points.length - 1];
  const lastDate = String(lastPoint.date || '').slice(5);

  return (
    <Svg width={width} height={height} accessibilityLabel="price chart">
      {ticks.map((tick, index) => (
        <React.Fragment key={`grid-${index}`}>
          <Path
            d={`M${PAD.left},${y(tick)} L${width - PAD.right},${y(tick)}`}
            stroke={theme.colors.chartGrid}
            strokeWidth={1}
            fill="none"
          />
          <SvgText
            x={PAD.left - 6}
            y={y(tick) + 4}
            fontSize={9}
            fill={theme.colors.textMuted}
            textAnchor="end">
            {formatCompact(tick)}
          </SvgText>
        </React.Fragment>
      ))}

      {showBand && bandPolygon ? (
        <Polygon points={bandPolygon} fill={theme.colors.chartFill} stroke="none" />
      ) : null}

      {areaPolygon ? <Polygon points={areaPolygon} fill={theme.colors.chartFill} stroke="none" /> : null}

      {historyPath ? (
        <Path
          testID="chart-history"
          d={historyPath}
          stroke={theme.colors.chartLine}
          strokeWidth={2}
          fill="none"
        />
      ) : null}

      {forecastPath ? (
        <Path
          testID="chart-forecast"
          d={forecastPath}
          stroke={theme.colors.forecastLine}
          strokeWidth={2}
          strokeDasharray="5,4"
          fill="none"
        />
      ) : null}

      {historyCount > 0 ? (
        <Circle
          cx={x(historyCount - 1)}
          cy={y(points[historyCount - 1].value)}
          r={3.5}
          fill={theme.colors.chartLine}
        />
      ) : null}

      <SvgText x={PAD.left} y={height - 6} fontSize={9} fill={theme.colors.textMuted}>
        {firstDate}
      </SvgText>
      <SvgText
        x={width - PAD.right}
        y={height - 6}
        fontSize={9}
        fill={theme.colors.textMuted}
        textAnchor="end">
        {lastDate}
      </SvgText>
    </Svg>
  );
}

const styles = StyleSheet.create({
  empty: {alignItems: 'center', justifyContent: 'center'},
});
