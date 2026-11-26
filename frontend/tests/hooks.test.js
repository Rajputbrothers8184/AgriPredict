import React from 'react';
import {Text, View} from 'react-native';
import {act, render, screen, waitFor} from '@testing-library/react-native';

import {useAsync} from '../src/hooks/useAsync';
import {ApiError} from '../src/services/apiClient';

function Harness({fetcher, immediate = true}) {
  const {data, error, loading, run} = useAsync(fetcher, {immediate});
  return (
    <View>
      <Text testID="loading">{loading ? 'loading' : 'idle'}</Text>
      <Text testID="data">{data === null || data === undefined ? 'none' : String(data)}</Text>
      <Text testID="error">{error ? error.messageKey : 'none'}</Text>
      <Text testID="retry" onPress={run}>
        retry
      </Text>
    </View>
  );
}

describe('useAsync', () => {
  it('exposes data after a successful fetch', async () => {
    const fetcher = jest.fn().mockResolvedValue('loaded');
    render(<Harness fetcher={fetcher} />);

    expect(screen.getByTestId('loading').props.children).toBe('loading');
    await waitFor(() => expect(screen.getByTestId('data').props.children).toBe('loaded'));
    expect(screen.getByTestId('loading').props.children).toBe('idle');
  });

  it('translates an ApiError into a message key', async () => {
    const fetcher = jest
      .fn()
      .mockRejectedValue(new ApiError('offline', {code: 'offline'}));
    render(<Harness fetcher={fetcher} />);

    await waitFor(() =>
      expect(screen.getByTestId('error').props.children).toBe('errors.network'),
    );
  });

  it('clears the error when the retry succeeds', async () => {
    const fetcher = jest
      .fn()
      .mockRejectedValueOnce(new ApiError('boom', {status: 500}))
      .mockResolvedValueOnce('recovered');
    render(<Harness fetcher={fetcher} />);

    await waitFor(() =>
      expect(screen.getByTestId('error').props.children).toBe('errors.server'),
    );

    await act(async () => {
      screen.getByTestId('retry').props.onPress();
    });

    await waitFor(() => expect(screen.getByTestId('data').props.children).toBe('recovered'));
    expect(screen.getByTestId('error').props.children).toBe('none');
  });

  it('does not fetch when immediate is false', async () => {
    const fetcher = jest.fn().mockResolvedValue('x');
    render(<Harness fetcher={fetcher} immediate={false} />);

    expect(fetcher).not.toHaveBeenCalled();
    expect(screen.getByTestId('data').props.children).toBe('none');
  });

  it('ignores a stale response that resolves after a newer call', async () => {
    let resolveFirst;
    let resolveSecond;
    const fetcher = jest
      .fn()
      .mockImplementationOnce(() => new Promise(resolve => (resolveFirst = resolve)))
      .mockImplementationOnce(() => new Promise(resolve => (resolveSecond = resolve)));

    function Double() {
      const {data, run} = useAsync(fetcher, {immediate: false});
      return (
        <View>
          <Text testID="value">{data === null || data === undefined ? 'none' : String(data)}</Text>
          <Text testID="go" onPress={() => {
            run('first');
            run('second');
          }}>
            go
          </Text>
        </View>
      );
    }

    render(<Double />);
    await act(async () => {
      screen.getByTestId('go').props.onPress();
    });

    // Resolve the newer call first, then the stale one.
    await act(async () => {
      resolveSecond('second');
    });
    await act(async () => {
      resolveFirst('first');
    });

    expect(screen.getByTestId('value').props.children).toBe('second');
  });
});
