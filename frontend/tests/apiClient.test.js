import api, {
  ApiError,
  configureApi,
  resetApiConfiguration,
} from '../src/services/apiClient';

const originalFetch = global.fetch;

function jsonResponse(body, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => (body === null ? '' : JSON.stringify(body)),
  };
}

describe('apiClient', () => {
  beforeEach(() => {
    resetApiConfiguration();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it('builds the URL from the configured base and drops empty query params', async () => {
    const calls = [];
    global.fetch = jest.fn(async (url, options) => {
      calls.push({url, options});
      return jsonResponse({ok: true});
    });

    await api.get('/farms', {query: {days: 30, district: '', missing: null, q: 'wheat'}});

    expect(calls[0].url).toContain('/api/v1/farms?');
    expect(calls[0].url).toContain('days=30');
    expect(calls[0].url).toContain('q=wheat');
    expect(calls[0].url).not.toContain('district=');
    expect(calls[0].url).not.toContain('missing=');
  });

  it('attaches the bearer token when one is configured', async () => {
    configureApi({getToken: () => 'token-abc'});
    let headers;
    global.fetch = jest.fn(async (url, options) => {
      headers = options.headers;
      return jsonResponse({ok: true});
    });

    await api.get('/auth/me');

    expect(headers.Authorization).toBe('Bearer token-abc');
  });

  it('does not send a token for public endpoints', async () => {
    configureApi({getToken: () => 'token-abc'});
    let headers;
    global.fetch = jest.fn(async (url, options) => {
      headers = options.headers;
      return jsonResponse({access_token: 'x'});
    });

    await api.publicPost('/auth/login', {email: 'a@b.c', password: 'Password1'});

    expect(headers.Authorization).toBeUndefined();
    expect(JSON.parse(global.fetch.mock.calls[0][1].body)).toEqual({
      email: 'a@b.c',
      password: 'Password1',
    });
  });

  it('maps an error envelope to ApiError with code and status', async () => {
    global.fetch = jest.fn(async () =>
      jsonResponse(
        {error: {code: 'validation_error', message: 'area_acres must be positive'}},
        422,
      ),
    );

    await expect(api.get('/farms')).rejects.toMatchObject({
      status: 422,
      code: 'validation_error',
      message: 'area_acres must be positive',
    });
  });

  it('reports a network failure as a retryable ApiError', async () => {
    global.fetch = jest.fn(async () => {
      throw new TypeError('Network request failed');
    });

    try {
      await api.get('/farms');
      throw new Error('should have thrown');
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError);
      expect(error.code).toBe('offline');
      expect(error.isRetryable).toBe(true);
    }
  });

  it('refreshes once on 401 and replays the request with the new token', async () => {
    let token = 'expired';
    let refreshed = 0;
    configureApi({
      getToken: () => token,
      onRefresh: async () => {
        refreshed += 1;
        token = 'fresh';
        return 'fresh';
      },
    });

    global.fetch = jest.fn(async (url, options) => {
      if (options.headers.Authorization === 'Bearer fresh') {
        return jsonResponse({id: 1});
      }
      return jsonResponse({error: {code: 'token_expired', message: 'expired'}}, 401);
    });

    await expect(api.get('/auth/me')).resolves.toEqual({id: 1});
    expect(refreshed).toBe(1);
  });

  it('gives up after a failed refresh and signals the session is over', async () => {
    const onUnauthorized = jest.fn();
    configureApi({
      getToken: () => 'expired',
      onRefresh: async () => null,
      onUnauthorized,
    });
    global.fetch = jest.fn(async () =>
      jsonResponse({error: {code: 'token_expired', message: 'expired'}}, 401),
    );

    await expect(api.get('/farms')).rejects.toMatchObject({code: 'session_expired'});
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });

  it('does not retry a 403 — that is a permission problem, not an expiry', async () => {
    const onRefresh = jest.fn();
    configureApi({getToken: () => 'token', onRefresh});
    global.fetch = jest.fn(async () =>
      jsonResponse({error: {code: 'forbidden', message: 'no access'}}, 403),
    );

    await expect(api.get('/farms')).rejects.toMatchObject({status: 403});
    expect(onRefresh).not.toHaveBeenCalled();
  });

  it('parses an empty 204 response as null', async () => {
    global.fetch = jest.fn(async () => jsonResponse(null, 204));
    await expect(api.delete('/farms/1')).resolves.toBeNull();
  });
});
