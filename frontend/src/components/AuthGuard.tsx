import { useEffect, useState, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { useAuth } from '@/lib/auth-context';
import { useOrganizationStore } from '@/lib/stores/organizations';
import { Loader2 } from 'lucide-react';
import { publicPaths } from '@/constants/paths';

interface AuthGuardProps {
  children: React.ReactNode;
}

export const AuthGuard = ({ children }: AuthGuardProps) => {
  const { isLoading: authLoading } = useAuth();
  const location = useLocation();

  // This state is crucial to prevent rendering children before the org check is complete
  const [canRenderChildren, setCanRenderChildren] = useState(false);
  const initializationAttempted = useRef(false);

  useEffect(() => {
    // Gooclaim fork — auth is performed by nginx auth-request validating
    // the bridge JWT cookie before any request reaches this app. Whether
    // authConfig.authEnabled is true or false in the bundle's runtime
    // config, the app must always run the same single flow: fetch
    // organizations from /users/me/organizations (nginx forwards the
    // tenant via X-Organization-Id) and render. The previous local-dev
    // branch skipped billing + diverged behavior, leaving stale
    // currentOrganization in store; that produced the "Failed to fetch"
    // cascade in the Sources screen.

    if (initializationAttempted.current) return;
    if (authLoading) return;
    initializationAttempted.current = true;

    useOrganizationStore.getState().initializeOrganizations()
      .then(async (fetchedOrganizations) => {
        if (fetchedOrganizations.length === 0) {
          console.warn('AuthGuard: no organizations returned — rendering anyway (bridge mode)');
          setCanRenderChildren(true);
          return;
        }
        try {
          await useOrganizationStore.getState().checkBillingStatus();
        } catch (e) {
          console.warn('AuthGuard: billing check failed, continuing:', e);
        }
        setCanRenderChildren(true);
      })
      .catch((error) => {
        console.error('AuthGuard: initializeOrganizations failed, rendering anyway:', error);
        setCanRenderChildren(true);
      });
  }, [authLoading]);

  // Show a loading spinner during the initial auth check or org fetch
  if (!canRenderChildren && (authLoading || !initializationAttempted.current)) {
     // A special check to prevent a flash of the loader on the onboarding page
    if (location.pathname === publicPaths.onboarding) {
      return null;
    }
    return (
      <div className="flex h-screen w-full items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  // Render children ONLY when the check is complete and successful
  if (canRenderChildren) {
    return <>{children}</>;
  }

  // Render nothing while redirecting or for unauthenticated users on public parts of the app
  return null;
};
