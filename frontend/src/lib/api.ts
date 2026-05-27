import { env } from '../config/env';
import { useOrganizationStore } from '@/lib/stores/organizations';
import { useCollectionsStore } from '@/lib/stores/collections';
import { useAPIKeysStore } from '@/lib/stores/apiKeys';
import { useAuthProvidersStore } from '@/lib/stores/authProviders';
import { toast } from 'sonner';
import { posthog } from '@/lib/posthog-provider';

// Define a token provider interface
interface TokenProvider {
  getToken: () => Promise<string | null>;
  clearToken?: () => void;
  isReady?: () => boolean;
}

// Default implementation that uses env variable
const defaultTokenProvider: TokenProvider = {
  getToken: async () => env.VITE_ACCESS_TOKEN || null,
  clearToken: () => {
    console.log('Default clearToken called - no effect in default provider');
  },
  isReady: () => true,
};

// Current token provider instance
let tokenProvider: TokenProvider = defaultTokenProvider;

// Request queue system
interface QueuedRequest {
  execute: () => Promise<Response>;
  resolve: (value: Response) => void;
  reject: (reason: any) => void;
}

const requestQueue: QueuedRequest[] = [];
let isProcessingQueue = false;

// Function to set a custom token provider
export const setTokenProvider = (provider: TokenProvider) => {
  tokenProvider = provider;

  // Try to process any queued requests when provider changes
  processQueue();

  // Set up a periodic check to process queue when auth becomes ready
  const checkInterval = setInterval(() => {
    if (provider.isReady && provider.isReady() && requestQueue.length > 0) {
      processQueue();
      clearInterval(checkInterval);
    }
  }, 100);

  // Clear interval after 10 seconds to prevent memory leak
  setTimeout(() => clearInterval(checkInterval), 10000);
};

// Process the request queue
const processQueue = async () => {
  // If we're already processing or the queue is empty, do nothing
  if (isProcessingQueue || requestQueue.length === 0) {
    return;
  }

  // Check if auth is ready
  const isAuthReady = tokenProvider.isReady ? tokenProvider.isReady() : true;
  if (!isAuthReady) {
    // Auth not ready yet, try again later
    setTimeout(processQueue, 100);
    return;
  }

  isProcessingQueue = true;

  console.log(`Processing request queue: ${requestQueue.length} requests`);

  while (requestQueue.length > 0) {
    const request = requestQueue.shift();
    if (!request) continue;

    try {
      const response = await request.execute();
      request.resolve(response);
    } catch (error) {
      request.reject(error);
    }
  }

  isProcessingQueue = false;
};

// Helper to queue a request if auth is not ready
const queueOrExecute = async (requestFn: () => Promise<Response>): Promise<Response> => {
  const isAuthReady = tokenProvider.isReady ? tokenProvider.isReady() : true;

  if (isAuthReady) {
    return requestFn();
  }

  // Queue the request
  return new Promise((resolve, reject) => {
    console.log('Queueing request until auth is ready');
    requestQueue.push({
      execute: requestFn,
      resolve,
      reject,
    });
  });
};

export const API_CONFIG = {
  baseURL: env.VITE_API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
} as const;

type ApiResponse<T = any> = Promise<Response>;
type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';

// Helper function to get PostHog session ID safely
const getPostHogSessionId = (): string | undefined => {
  try {
    if (posthog && typeof posthog.get_session_id === 'function') {
      return posthog.get_session_id();
    }
  } catch (error) {
    console.debug('PostHog session ID error:', error);
  }
  return undefined;
};

// Get headers — Gooclaim fork uses cookie-only auth.
const getHeaders = async (): Promise<Record<string, string>> => {
  const { currentOrganization } = useOrganizationStore.getState();

  // Gooclaim fork — do NOT send `Authorization: Bearer <token>`. In
  // local-dev mode (which the Gooclaim bundle ships with — auth.ts
  // resolves authConfig.authEnabled from window.ENV.AUTH_ENABLED=false)
  // auth-context.getToken() returns the literal string "dev-mode-token".
  // That value would land in the Authorization header and
  // gooclaim-auth's `_extract_bridge_token` prioritizes Authorization
  // over the cookie — so a request that *would* have validated by
  // cookie gets a 401 instead, racing with not-yet-ready getToken()
  // calls that returned null. The browser sees alternating
  // 200/401/Failed-to-fetch on Sources / Billing / API Keys / etc.
  //
  // Same reasoning for X-Organization-ID — nginx auth-request injects
  // the canonical X-Organization-Id from the bridge JWT.
  void currentOrganization;

  return { ...API_CONFIG.headers };
};

// Helper function to clear organization-specific state when auto-switching
const clearOrganizationSpecificState = () => {
  console.log("🧹 [AutoSwitch] Clearing organization-specific state");

  // Clear collections store
  useCollectionsStore.getState().clearCollections();

  // Clear API keys store
  useAPIKeysStore.getState().clearAPIKeys();

  // Clear auth provider connections store
  useAuthProvidersStore.getState().clearAuthProviderConnections();

  // Add any other organization-specific stores here in the future
};

// Helper to check and handle organization mismatch
const handleOrganizationMismatch = async (responseData: any, method: HttpMethod): Promise<boolean> => {
  // Only auto-switch on GET requests to avoid side effects
  if (method !== 'GET') {
    return false;
  }

  // Don't auto-switch on homepage to avoid conflicts with manual org switching
  if (window.location.pathname === '/') {
    return false;
  }

  const { currentOrganization, organizations, switchOrganization } = useOrganizationStore.getState();

  if (!currentOrganization || !organizations.length) {
    return false;
  }

  // Extract organization_id from response data
  let responseOrgId: string | null = null;

  if (responseData && typeof responseData === 'object') {
    // Check if response is a single object with organization_id
    if (responseData.organization_id) {
      responseOrgId = responseData.organization_id;
    }
    // Check if response is an array and get org_id from first item
    else if (Array.isArray(responseData) && responseData.length > 0 && responseData[0].organization_id) {
      responseOrgId = responseData[0].organization_id;
    }
  }

  // If no organization_id found in response, or it matches current org, no action needed
  if (!responseOrgId || responseOrgId === currentOrganization.id) {
    return false;
  }

  // Check if user has access to the response's organization
  const targetOrg = organizations.find(org => org.id === responseOrgId);
  if (!targetOrg) {
    console.warn('Response contains organization_id that user does not have access to:', responseOrgId);
    return false;
  }

  // Clear organization-specific state before switching
  clearOrganizationSpecificState();

  // Switch to the target organization
  console.log(`🔄 Auto-switching from ${currentOrganization.name} to ${targetOrg.name} for this resource`);
  switchOrganization(responseOrgId);

  // Show user feedback
  toast.info(`Switched to "${targetOrg.name}" to view this resource`, {
    duration: 4000,
  });

  return true; // Indicate that we switched organizations
};

// Shared HTTP request function to eliminate duplication
const makeRequest = async <T>(
  method: HttpMethod,
  endpoint: string,
  options?: {
    data?: any;
    params?: Record<string, any>;
    signal?: AbortSignal;
  },
  _isRetry: boolean = false
): ApiResponse<T> => {
  const requestFn = async () => {
    const url = new URL(`${API_CONFIG.baseURL}${endpoint}`);
    if (options?.params) {
      Object.entries(options.params).forEach(([key, value]) =>
        url.searchParams.append(key, String(value))
      );
    }

    let headers = await getHeaders();

    const fetchOptions: RequestInit = {
      method,
      headers,
      signal: options?.signal,
      // Send cookies on every request — required for the Gooclaim bridge
      // JWT flow (cookie 'gooclaim_airweave_bridge' set by gooclaim-auth's
      // /v1/auth/airweave-sso-mint). Without this, browser strips the
      // cookie from XHR and nginx auth-request 401s every API call.
      credentials: 'include',
    };

    // Add body for methods that support it
    if (options?.data && method !== 'GET' && method !== 'DELETE') {
      fetchOptions.body = JSON.stringify(options.data);
    }

    let response = await fetch(url.toString(), fetchOptions);

    // Handle 401/403 by attempting token refresh once
    if ((response.status === 401 || response.status === 403) && tokenProvider.clearToken) {
      console.log(`Got ${response.status} error, attempting token refresh`);
      tokenProvider.clearToken(); // Clear the cached token

      // Get fresh headers with new token
      headers = await getHeaders();

      if (headers.Authorization) {
        console.log('Retrying request with fresh token');
        // Retry with new token
        fetchOptions.headers = headers;
        const retryResponse = await fetch(url.toString(), fetchOptions);

        // If still 403 after retry, refresh org context so the UI
        // reflects revoked permissions (buttons disable, sections hide).
        if (retryResponse.status === 403) {
          try {
            const { initializeOrganizations } = useOrganizationStore.getState();
            await initializeOrganizations();
          } catch (e) {
            console.error('Failed to refresh organization context:', e);
          }
        }

        response = retryResponse;
      }
    }

    // Handle organization auto-switching for successful GET requests
    if (response.ok && method === 'GET' && !_isRetry) {
      try {
        // Clone the response so we can read it twice
        const responseClone = response.clone();
        const responseData = await responseClone.json();

        // Check if we need to switch organizations
        const didSwitch = await handleOrganizationMismatch(responseData, method);

        if (didSwitch) {
          // Retry the request with the new organization context
          console.log('🔄 Retrying request with new organization context');
          return await makeRequest(method, endpoint, options, true); // Mark as retry to prevent infinite loops
        }
      } catch (error) {
        // If we can't parse JSON, just continue with original response
        console.warn('Could not parse response for organization check:', error);
      }
    }

    return response;
  };

  return queueOrExecute(requestFn);
};

// ---- SSE support (unified with the same baseURL, headers, and token-refresh) ----

type SSEHandlers = {
  onMessage: (msg: MessageEvent) => void;
  onOpen?: (res: Response) => void | Promise<void>;
  onError?: (err: any) => void;
  onClose?: () => void;
};

const waitForAuthReady = async () => {
  if (tokenProvider.isReady && !tokenProvider.isReady()) {
    await new Promise<void>((resolve) => {
      const started = Date.now();
      const interval = setInterval(() => {
        if (!tokenProvider.isReady || tokenProvider.isReady()) {
          clearInterval(interval);
          resolve();
        }
        // Hard cap to avoid dangling intervals
        if (Date.now() - started > 10_000) {
          clearInterval(interval);
          resolve();
        }
      }, 100);
    });
  }
};

export const apiClient = {
  clearToken: () => {
    if (tokenProvider.clearToken) {
      tokenProvider.clearToken();
    } else {
      console.warn('No clearToken method available in current tokenProvider');
    }
  },

  // Add getToken method to get current auth token
  getToken: async (): Promise<string | null> => {
    return tokenProvider.getToken();
  },

  async get<T>(endpoint: string, params?: Record<string, any>): ApiResponse<T> {
    return makeRequest<T>('GET', endpoint, { params });
  },

  async post<T>(endpoint: string, data?: any, params?: Record<string, any>): ApiResponse<T> {
    // Backwards-compatible options: allow (endpoint, data, params) or (endpoint, data, { params, signal })
    const raw = params as any;
    const options = {
      data,
      params: raw && raw.params ? raw.params : (raw && !raw.signal ? raw : undefined),
      signal: raw && raw.signal ? raw.signal : undefined,
    } as { data?: any; params?: Record<string, any>; signal?: AbortSignal };
    return makeRequest<T>('POST', endpoint, options);
  },

  async put<T>(endpoint: string, params?: Record<string, any>, data?: any): ApiResponse<T> {
    return makeRequest<T>('PUT', endpoint, { data, params });
  },

  async patch<T>(endpoint: string, data?: any, params?: Record<string, any>): ApiResponse<T> {
    return makeRequest<T>('PATCH', endpoint, { data, params });
  },

  async delete<T>(endpoint: string, params?: Record<string, any>): ApiResponse<T> {
    return makeRequest<T>('DELETE', endpoint, { params });
  },

  // New: SSE method that uses the same baseURL + headers + token refresh semantics
  async sse(
    endpoint: string,
    handlers: SSEHandlers,
    options?: {
      params?: Record<string, any>;
      signal?: AbortSignal;
      method?: 'GET' | 'POST'; // usually GET for SSE
      openWhenHidden?: boolean;
    }
  ): Promise<void> {
    await waitForAuthReady();

    const url = new URL(`${API_CONFIG.baseURL}${endpoint}`);
    if (options?.params) {
      Object.entries(options.params).forEach(([k, v]) =>
        url.searchParams.append(k, String(v))
      );
    }

    const { fetchEventSource } = await import('@microsoft/fetch-event-source');

    // Bridge the caller's AbortSignal into our own so we can cleanly abort
    const controller = new AbortController();
    if (options?.signal) {
      options.signal.addEventListener('abort', () => controller.abort(), { once: true });
    }

    return fetchEventSource(url.toString(), {
      method: options?.method ?? 'GET',
      signal: controller.signal,
      openWhenHidden: options?.openWhenHidden ?? true,

      // Initial headers (Authorization + X-Organization-ID)
      headers: await getHeaders(),

      onopen: async (res) => {
        if (handlers.onOpen) await handlers.onOpen(res);
        if (res.status === 401 || res.status === 403) {
          // force a refresh on first unauthorized open, then let the library retry
          tokenProvider.clearToken?.();
          throw new Error('Unauthorized; retrying with refreshed token');
        }
        if (!res.ok) {
          throw new Error(`SSE failed with status ${res.status}`);
        }
      },

      onmessage: handlers.onMessage as any,

      onerror: (err) => {
        handlers.onError?.(err);
        // Throw to allow the library to decide retry/stop behavior
        throw err;
      },

      // Ensure each (re)connect uses fresh headers and one-shot token refresh
      fetch: async (input, init) => {
        let headers = await getHeaders();
        let res = await fetch(input, { ...init, headers, credentials: 'include' });

        if ((res.status === 401 || res.status === 403) && tokenProvider.clearToken) {
          tokenProvider.clearToken();
          headers = await getHeaders();
          res = await fetch(input, { ...init, headers, credentials: 'include' });
        }
        return res;
      },
    }).finally(() => {
      handlers.onClose?.();
    });
  },
};
