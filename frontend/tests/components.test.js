import React from 'react';
import {render, screen, fireEvent} from '@testing-library/react-native';

import {Badge, Button, Input, Row, StatTile} from '../src/components/ui';
import {Path} from 'react-native-svg';

import PriceChart from '../src/components/PriceChart';
import {LocalizationProvider} from '../src/context/LocalizationContext';
import {ThemeProvider} from '../src/context/ThemeContext';

function wrap(element) {
  return (
    <ThemeProvider initialTheme="light">
      <LocalizationProvider initialLanguage="en">{element}</LocalizationProvider>
    </ThemeProvider>
  );
}

describe('Button', () => {
  it('fires onPress', () => {
    const onPress = jest.fn();
    render(wrap(<Button title="Save" onPress={onPress} testID="btn" />));
    fireEvent.press(screen.getByTestId('btn'));
    expect(onPress).toHaveBeenCalledTimes(1);
  });

  it('does not fire when disabled', () => {
    const onPress = jest.fn();
    render(wrap(<Button title="Save" onPress={onPress} disabled testID="btn" />));
    fireEvent.press(screen.getByTestId('btn'));
    expect(onPress).not.toHaveBeenCalled();
  });

  it('exposes a busy state while loading and hides the label', () => {
    render(wrap(<Button title="Save" onPress={() => {}} loading testID="btn" />));
    expect(screen.getByTestId('btn').props.accessibilityState.busy).toBe(true);
    expect(screen.queryByText('Save')).toBeNull();
  });
});

describe('form fields', () => {
  it('shows a required marker and the error message', () => {
    render(
      wrap(
        <Input
          label="Area (acres)"
          required
          value=""
          onChangeText={() => {}}
          error="Enter a number greater than zero."
        />,
      ),
    );
    expect(screen.getByText('Area (acres) *')).toBeTruthy();
    expect(screen.getByText('Enter a number greater than zero.')).toBeTruthy();
  });

  it('passes typed text to onChangeText', () => {
    const onChangeText = jest.fn();
    render(wrap(<Input label="Name" value="" onChangeText={onChangeText} testID="name" />));
    fireEvent.changeText(screen.getByTestId('name'), 'Lahore plot');
    expect(onChangeText).toHaveBeenCalledWith('Lahore plot');
  });
});

describe('presentational pieces', () => {
  it('renders a stat tile with label, value and hint', () => {
    render(wrap(<StatTile label="Profit" value="PKR 37,000" hint="Margin: 60.7%" />));
    expect(screen.getByText('Profit')).toBeTruthy();
    expect(screen.getByText('PKR 37,000')).toBeTruthy();
    expect(screen.getByText('Margin: 60.7%')).toBeTruthy();
  });

  it('renders a badge label', () => {
    render(wrap(<Badge label="Harvested" tone="success" />));
    expect(screen.getByText('Harvested')).toBeTruthy();
  });

  it('renders a label/value row', () => {
    render(wrap(<Row label="Cost" value="PKR 24,000" />));
    expect(screen.getByText('Cost')).toBeTruthy();
    expect(screen.getByText('PKR 24,000')).toBeTruthy();
  });
});

describe('PriceChart', () => {
  const series = [
    {date: '2026-11-01', value: 4000},
    {date: '2026-11-02', value: 4100},
    {date: '2026-11-03', value: 4300},
  ];

  it('draws a history path and a forecast path', () => {
    const view = render(
      wrap(
        <PriceChart
          series={series}
          forecast={[
            {date: '2026-11-04', value: 4400, lower: 4300, upper: 4500},
            {date: '2026-11-05', value: 4500, lower: 4350, upper: 4650},
          ]}
          width={320}
        />,
      ),
    );
    // Path also draws gridlines, so select the series by testID rather than by
    // index — an index would silently break if a gridline is added.
    const dashed = view.UNSAFE_root.findAllByType(Path).filter(
      node => node.props.strokeDasharray === '5,4',
    );
    expect(dashed).toHaveLength(1);

    const history = screen.getByTestId('chart-history');
    const forecastLine = screen.getByTestId('chart-forecast');
    expect(history.props.d).toMatch(/^M\d/);
    expect(forecastLine.props.d).toMatch(/^M\d/);
    // The forecast line must begin at the last observed point, not float free.
    // Compare coordinates only; the command letter differs (M vs L) by design.
    const coordinates = command => command.replace(/^[ML]/, '');
    expect(coordinates(forecastLine.props.d.split(' ')[0])).toBe(
      coordinates(history.props.d.split(' ').slice(-1)[0]),
    );
  });

  it('handles a flat series without dividing by zero', () => {
    const flat = [
      {date: '2026-11-01', value: 4000},
      {date: '2026-11-02', value: 4000},
      {date: '2026-11-03', value: 4000},
    ];
    expect(() => render(wrap(<PriceChart series={flat} width={320} />))).not.toThrow();
  });

  it('renders an empty placeholder with no data', () => {
    const view = render(wrap(<PriceChart series={[]} width={320} />));
    expect(view.UNSAFE_root.findAllByType(Path)).toHaveLength(0);
  });

  it('ignores non-numeric values instead of producing NaN coordinates', () => {
    const messy = [...series, {date: '2026-11-04', value: null}, {date: '2026-11-05', value: 'x'}];
    const view = render(wrap(<PriceChart series={messy} width={320} />));
    const paths = view.UNSAFE_root.findAllByType(Path);
    expect(paths.length).toBeGreaterThan(0);
    paths.forEach(node => expect(String(node.props.d)).not.toMatch(/NaN/));
  });
});
