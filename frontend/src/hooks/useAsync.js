/**
 * Data-fetching hook with explicit loading / error / data states.
 *
 * Why not a library: three states plus retry covers every screen here, and this
 * implementation is small enough to reason about. It also cancels cleanly on
 * unmount, which prevents the "setState on an unmounted component" warning that
 * plagues navigation-heavy apps.
 */

import {useCallback, useEffect, useRef, useState} from 'react';

import {ApiError} from '../services/apiClient';
import {mapApiError} from '../utils/errors';

export function useAsync(asyncFunction, {immediate = true, deps = [], initialData = null} = {}) {
  const [data, setData] = useState(initialData);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(immediate);
  const mounted = useRef(true);
  const callId = useRef(0);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const run = useCallback(async (...args) => {
    const id = ++callId.current;
    setLoading(true);
    setError(null);
    try {
      const result = await asyncFunction(...args);
      // Ignore a stale response that resolved after a newer call started.
      if (mounted.current && id === callId.current) {
        setData(result);
        setLoading(false);
      }
      return result;
    } catch (caught) {
      if (mounted.current && id === callId.current) {
        setError(caught instanceof ApiError ? mapApiError(caught) : caught);
        setLoading(false);
      }
      return undefined;
    }
  }, deps); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (immediate) {
      run();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return {data, error, loading, run, setData};
}

export default useAsync;
