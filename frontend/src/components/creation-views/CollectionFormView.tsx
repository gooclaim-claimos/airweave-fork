import React, { useState, useEffect } from 'react';
import { useCollectionCreationStore } from '@/stores/collectionCreationStore';
import { apiClient } from '@/lib/api';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { useTheme } from '@/lib/theme-provider';
import { HelpCircle, Lock, Users } from 'lucide-react';
import { LIBRARY_LABEL, LIBRARY_MEANING, type LibraryAudience } from '@/components/collection/LibraryBadge';
import { ValidatedInput } from '@/components/ui/validated-input';
import { collectionNameValidation } from '@/lib/validation/rules';

interface CollectionFormViewProps {
  humanReadableId: string;
}

export const CollectionFormView: React.FC<CollectionFormViewProps> = ({ humanReadableId }) => {
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === 'dark';

  const {
    collectionName,
    selectedSource,
    sourceName,
    setCollectionData,
    setCollectionId,
    setAudience,
    setStep
  } = useCollectionCreationStore();

  const [name, setName] = useState(collectionName);
  // Gooclaim: who these documents may answer. Starts EMPTY on purpose — the
  // uploader chooses; nothing is chosen for them (the server refuses none).
  const [audience, setLocalAudience] = useState<LibraryAudience | null>(null);
  const [isCreating, setIsCreating] = useState(false);

  // Update store when name changes
  useEffect(() => {
    setCollectionData(name);
  }, [name, setCollectionData]);

  const handleCreate = async () => {
    if (!name.trim()) {
      toast.error('Please enter a collection name');
      return;
    }
    if (!audience) {
      toast.error('Choose who these documents may answer');
      return;
    }

    setIsCreating(true);
    try {
      // Pass the readable_id the modal has already generated so the
      // collection that lands in the DB matches whatever the next step
      // uses as its identifier (e.g. NativeUploadView's connection_id =
      // humanReadableId). Without this, the backend picks its own random
      // suffix and the Native Upload commit flow ends up creating a
      // second collection with the frontend's id — leaving the original
      // one stuck in "Needs Source" state.
      const response = await apiClient.post('/collections', {
        name: name.trim(),
        description: `Collection for ${name.trim()}`,
        readable_id: humanReadableId || undefined,
        audience,
      });

      if (!response.ok) {
        throw new Error('Failed to create collection');
      }

      const collection = await response.json();

      // Store collection data
      setCollectionData(name.trim());
      setCollectionId(collection.readable_id || collection.id);
      setAudience(audience);

      // Move to next step based on whether source is pre-selected.
      // Gooclaim native upload uses its own step instead of the generic
      // source-config form (no auth fields, files come in via a separate
      // multipart endpoint) — same special case as SourceSelectView's
      // handleSelectSource, which this path bypasses when the source was
      // already chosen before the collection-name step ran.
      if (selectedSource === 'gooclaim_upload') {
        setStep('native-upload');
      } else if (selectedSource) {
        setStep('source-config');
      } else {
        setStep('source-select');
      }

    } catch (error) {
      console.error('Error creating collection:', error);
      toast.error('Failed to create collection');
    } finally {
      setIsCreating(false);
    }
  };

  return (
    <div className="h-full flex flex-col">
      <div className="px-8 py-10 flex-1">
        <div className="space-y-8">
          {/* Header */}
          <div>
            <h2 className="text-2xl font-semibold text-gray-900 dark:text-white">
              Create Collection
            </h2>
            <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
              Collections group your data sources for unified search
            </p>
          </div>

          {/* Form */}
          <div className="space-y-6">
            <div>
              <label
                htmlFor="collection-name"
                className={cn(
                  "block text-sm font-medium mb-2",
                  isDark ? "text-gray-200" : "text-gray-700"
                )}
              >
                Name
              </label>
              <ValidatedInput
                id="collection-name"
                type="text"
                placeholder="Acme's HR Applications"
                value={name}
                onChange={setName}
                onKeyDown={(e) => e.key === 'Enter' && !isCreating && handleCreate()}
                autoFocus
                validation={collectionNameValidation}
                className={cn(
                  "focus:border-gray-400 dark:focus:border-gray-600",
                  isDark
                    ? "bg-gray-800 border-gray-700 text-white placeholder:text-gray-500"
                    : "bg-white border-gray-200 text-gray-900 placeholder:text-gray-400"
                )}
              />
            </div>

            {/* Gooclaim: which library — required, nothing preselected */}
            <fieldset>
              <legend
                className={cn(
                  "block text-sm font-medium mb-2",
                  isDark ? "text-gray-200" : "text-gray-700"
                )}
              >
                Who may these documents answer?
              </legend>
              <div className="grid gap-2" role="radiogroup" aria-required="true">
                {(['members', 'staff'] as LibraryAudience[]).map((option) => {
                  const Icon = option === 'staff' ? Lock : Users;
                  const chosen = audience === option;
                  return (
                    <label
                      key={option}
                      className={cn(
                        "flex items-start gap-3 rounded-lg border p-3 cursor-pointer transition-colors",
                        chosen
                          ? "border-blue-600 bg-blue-50 dark:bg-blue-950/40"
                          : isDark
                            ? "border-gray-700 hover:border-gray-500"
                            : "border-gray-200 hover:border-gray-400"
                      )}
                    >
                      <input
                        type="radio"
                        name="library-audience"
                        value={option}
                        checked={chosen}
                        onChange={() => setLocalAudience(option)}
                        className="mt-1"
                      />
                      <Icon className="h-4 w-4 mt-0.5 flex-shrink-0 opacity-70" aria-hidden />
                      <span>
                        <span className="block text-sm font-medium">{LIBRARY_LABEL[option]}</span>
                        <span className={cn("block text-xs mt-0.5", isDark ? "text-gray-400" : "text-gray-500")}>
                          {LIBRARY_MEANING[option]}
                        </span>
                      </span>
                    </label>
                  );
                })}
              </div>
              <p className={cn("text-xs mt-2", isDark ? "text-gray-500" : "text-gray-500")}>
                This cannot be changed later. To move a document, upload it to a library made for the other audience.
              </p>
            </fieldset>

            {/* Help section with hover info */}
            <div className="flex items-start gap-2 group">
              <div className="relative">
                <HelpCircle className={cn(
                  "h-4 w-4 mt-0.5 flex-shrink-0 transition-all cursor-help",
                  isDark
                    ? "text-gray-500 group-hover:text-blue-400"
                    : "text-gray-400 group-hover:text-blue-600"
                )} />

                {/* Hover tooltip */}
                <div className={cn(
                  "absolute left-0 top-6 z-50 w-80 p-4 rounded-lg shadow-xl",
                  "opacity-0 invisible group-hover:opacity-100 group-hover:visible",
                  "transition-all duration-200 transform group-hover:translate-y-0 translate-y-1",
                  isDark
                    ? "bg-gray-800 border border-gray-700"
                    : "bg-white border border-gray-200"
                )}>
                  <div className="space-y-3">
                    <p className={cn(
                      "text-sm font-medium",
                      isDark ? "text-white" : "text-gray-900"
                    )}>
                      What is a collection?
                    </p>
                    <p className={cn(
                      "text-xs leading-relaxed",
                      isDark ? "text-gray-400" : "text-gray-600"
                    )}>
                      A collection is like a folder that groups related data sources. It can include multiple sources from a user, organization, or project. When your agent searches, it queries all sources in the collection at once.
                    </p>
                    <div className={cn(
                      "text-xs space-y-1 pt-2 border-t",
                      isDark ? "border-gray-700" : "border-gray-200"
                    )}>
                      <p className={cn(isDark ? "text-gray-500" : "text-gray-500")}>
                        <span className="font-medium">Example:</span> Group all HR tools (Jira, Notion, Google Drive) at Acme Corp into one searchable collection
                      </p>
                    </div>
                  </div>
                </div>
              </div>

              <p className={cn(
                "text-sm",
                isDark ? "text-gray-500" : "text-gray-500"
              )}>
                What is a collection?
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Bottom action */}
      <div className={cn(
        "px-8 py-6 border-t",
        isDark ? "border-gray-800" : "border-gray-200"
      )}>
        <button
          onClick={handleCreate}
          disabled={!name.trim() || name.trim().length < 4 || name.trim().length > 64 || !audience || isCreating}
          className={cn(
            "w-full py-2 px-4 rounded-lg text-sm font-medium",
            "transition-all",
            "disabled:opacity-50 disabled:cursor-not-allowed",
            name.trim().length >= 4 && name.trim().length <= 64 && audience && !isCreating
              ? "bg-blue-600 hover:bg-blue-700 text-white"
              : "bg-gray-300 dark:bg-gray-700 text-gray-500 dark:text-gray-400"
          )}
        >
          {isCreating ? 'Creating...' : 'Next'}
        </button>
      </div>
    </div>
  );
};
