/**
 * Gooclaim: which library a collection is — who its documents may answer.
 *
 * "members": the members' library — anything in it may be used to answer a
 * member. "staff": only Orion, the staff coworker, searches it. Set when the
 * collection is made and never changed (the server refuses both a missing
 * choice and a change), so the badge is shown wherever a collection is named.
 */
import { Lock, Users } from 'lucide-react';

import { cn } from '@/lib/utils';

export type LibraryAudience = 'members' | 'staff';

export const LIBRARY_LABEL: Record<LibraryAudience, string> = {
  members: 'Members',
  staff: 'Staff only',
};

export const LIBRARY_MEANING: Record<LibraryAudience, string> = {
  members: "Members' library — these documents may be used to answer your members.",
  staff: 'Staff library — only Orion, your staff coworker, searches these. Never shown to members.',
};

export function LibraryBadge({ audience, className }: { audience?: LibraryAudience | null; className?: string }) {
  if (!audience) return null; // never guess which library it is
  const Icon = audience === 'staff' ? Lock : Users;
  return (
    <span
      title={LIBRARY_MEANING[audience]}
      className={cn(
        'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium leading-none whitespace-nowrap',
        audience === 'staff'
          ? 'bg-amber-100 text-amber-900 dark:bg-amber-900/40 dark:text-amber-200'
          : 'bg-sky-100 text-sky-900 dark:bg-sky-900/40 dark:text-sky-200',
        className,
      )}
    >
      <Icon className="h-3 w-3" aria-hidden />
      {LIBRARY_LABEL[audience]}
    </span>
  );
}
