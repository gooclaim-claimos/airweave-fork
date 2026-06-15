/**
 * NativeUploadView — Gooclaim Data Sources file upload flow.
 *
 * Picks up the creation-modal flow after the user selects the
 * "Native Upload" tile on `source-select`. The connection_id is derived
 * from the collection's human-readable id so the backend storage path
 * stays stable across reloads (POST /api/uploads/{connection_id}).
 *
 * MVP scope (matches Phase 3 plan): drag-drop or click-to-pick file
 * upload + sidecar-aware listing of files already in the bucket.
 * Source-connection registration in /source-connections + sync
 * triggering land in a follow-up phase.
 */

import React, { useEffect, useRef, useState } from 'react';
import { ArrowLeft, FileText, Loader2, Upload, X } from 'lucide-react';

import { apiClient } from '@/lib/api';
import { cn } from '@/lib/utils';
import { useTheme } from '@/lib/theme-provider';
import { useCollectionCreationStore } from '@/stores/collectionCreationStore';

interface NativeUploadViewProps {
  humanReadableId: string;
}

interface UploadListItem {
  upload_id: string;
  file_name: string;
  file_type: string;
  size: number;
  uploaded_at: string;
  uploaded_by?: string | null;
  description?: string | null;
}

interface UploadFileResponse extends UploadListItem {
  connection_id: string;
  stored_path: string;
}

const SUPPORTED_EXTS = [
  '.pdf', '.docx', '.doc', '.pptx', '.txt', '.md',
  '.html', '.htm', '.csv', '.json',
];

const MAX_BYTES = 50 * 1024 * 1024;

function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function fmtDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export const NativeUploadView: React.FC<NativeUploadViewProps> = ({ humanReadableId }) => {
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === 'dark';

  const setStep = useCollectionCreationStore((s) => s.setStep);
  const collectionName = useCollectionCreationStore((s) => s.collectionName);

  // The connection_id the upload endpoint scopes by. We keep it stable
  // across renders by deriving it once from the collection's readable id.
  const connectionId = humanReadableId || 'untitled';

  const [isCommitting, setIsCommitting] = useState(false);

  const [items, setItems] = useState<UploadListItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // ── Initial + post-upload listing ────────────────────────────────
  const refreshList = async () => {
    setIsLoading(true);
    try {
      const resp = await apiClient.get(`/uploads/${encodeURIComponent(connectionId)}`);
      if (!resp.ok) throw new Error(`List failed: HTTP ${resp.status}`);
      const data = await resp.json();
      setItems(Array.isArray(data?.items) ? data.items : []);
    } catch (err) {
      console.error('NativeUploadView: list error', err);
      setErrorMsg(err instanceof Error ? err.message : 'Failed to load uploads.');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    refreshList();
  }, [connectionId]);

  // ── Upload one file ─────────────────────────────────────────────
  const uploadOne = async (file: File): Promise<UploadFileResponse> => {
    const ext = '.' + (file.name.split('.').pop() || '').toLowerCase();
    if (!SUPPORTED_EXTS.includes(ext)) {
      throw new Error(`Unsupported extension ${ext}. Supported: ${SUPPORTED_EXTS.join(', ')}`);
    }
    if (file.size === 0) {
      throw new Error(`${file.name} is empty.`);
    }
    if (file.size > MAX_BYTES) {
      throw new Error(`${file.name} is over the 50 MB limit.`);
    }

    const form = new FormData();
    form.append('file', file);

    const resp = await apiClient.postFormData(
      `/uploads/${encodeURIComponent(connectionId)}`,
      form,
    );
    if (!resp.ok) {
      const text = await resp.text();
      throw new Error(`Upload failed (HTTP ${resp.status}): ${text}`);
    }
    return (await resp.json()) as UploadFileResponse;
  };

  const handleFiles = async (files: FileList | File[]) => {
    setErrorMsg(null);
    setIsUploading(true);
    try {
      const list = Array.from(files);
      for (const f of list) {
        await uploadOne(f);
      }
      await refreshList();
    } catch (err) {
      console.error('NativeUploadView: upload error', err);
      setErrorMsg(err instanceof Error ? err.message : 'Upload failed.');
    } finally {
      setIsUploading(false);
    }
  };

  // ── DnD handlers ─────────────────────────────────────────────────
  const onDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragActive(true);
  };
  const onDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragActive(false);
  };
  const onDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragActive(false);
    if (e.dataTransfer.files?.length) {
      handleFiles(e.dataTransfer.files);
    }
  };

  // ── Render ───────────────────────────────────────────────────────
  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center gap-3 px-6 py-4 border-b border-border">
        <button
          onClick={() => setStep('source-select')}
          className={cn(
            'p-1.5 rounded-lg transition-colors',
            isDark ? 'hover:bg-gray-800 text-gray-400' : 'hover:bg-gray-100 text-gray-500',
          )}
          aria-label="Back to source selection"
        >
          <ArrowLeft className="w-4 h-4" />
        </button>
        <div className="flex-1">
          <h2 className="text-base font-semibold">Native Upload</h2>
          <p className={cn('text-xs', isDark ? 'text-gray-400' : 'text-gray-500')}>
            Connection: <code className="font-mono">{connectionId}</code>
          </p>
        </div>
      </div>

      {/* Drop zone */}
      <div className="p-6">
        <div
          onDragOver={onDragOver}
          onDragLeave={onDragLeave}
          onDrop={onDrop}
          onClick={() => fileInputRef.current?.click()}
          className={cn(
            'border-2 border-dashed rounded-xl px-8 py-10 text-center cursor-pointer transition-colors',
            dragActive
              ? 'border-sky-500 bg-sky-500/10'
              : isDark
                ? 'border-gray-700 hover:border-gray-600'
                : 'border-gray-300 hover:border-gray-400',
          )}
        >
          <Upload
            className={cn(
              'w-8 h-8 mx-auto mb-3',
              isDark ? 'text-gray-400' : 'text-gray-500',
            )}
          />
          <p className="text-sm font-medium">
            Drop files here or <span className="text-sky-600 dark:text-sky-400">browse</span>
          </p>
          <p className={cn('text-xs mt-1', isDark ? 'text-gray-500' : 'text-gray-500')}>
            PDF · DOCX · PPTX · TXT · MD · HTML · CSV · JSON · up to 50 MB
          </p>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="hidden"
            accept={SUPPORTED_EXTS.join(',')}
            onChange={(e) => {
              if (e.target.files?.length) handleFiles(e.target.files);
              e.target.value = '';
            }}
          />
        </div>

        {(isUploading || isLoading) && (
          <div className="flex items-center gap-2 mt-3 text-sm">
            <Loader2 className="w-4 h-4 animate-spin" />
            <span>{isUploading ? 'Uploading…' : 'Loading existing uploads…'}</span>
          </div>
        )}

        {errorMsg && (
          <div className="flex items-start gap-2 mt-3 px-3 py-2 rounded-md bg-red-50 dark:bg-red-950 text-sm text-red-800 dark:text-red-200">
            <X className="w-4 h-4 mt-0.5 flex-shrink-0" />
            <div className="flex-1 break-words">{errorMsg}</div>
            <button
              onClick={() => setErrorMsg(null)}
              className="text-red-700 dark:text-red-300 hover:underline text-xs"
            >
              dismiss
            </button>
          </div>
        )}
      </div>

      {/* Uploads list */}
      <div className="flex-1 overflow-y-auto px-6 pb-6">
        <h3 className={cn('text-xs uppercase tracking-wider mb-2', isDark ? 'text-gray-500' : 'text-gray-500')}>
          Uploaded files {items.length > 0 && `(${items.length})`}
        </h3>
        {items.length === 0 ? (
          <p className={cn('text-sm italic', isDark ? 'text-gray-500' : 'text-gray-400')}>
            No files yet — drop your first one above.
          </p>
        ) : (
          <ul className="space-y-1.5">
            {items.map((it) => (
              <li
                key={it.upload_id}
                className={cn(
                  'flex items-center gap-3 px-3 py-2 rounded-md border',
                  isDark ? 'border-gray-800 bg-gray-900/40' : 'border-gray-200 bg-gray-50',
                )}
              >
                <FileText className={cn('w-4 h-4 flex-shrink-0', isDark ? 'text-gray-400' : 'text-gray-500')} />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium truncate">{it.file_name}</div>
                  <div className={cn('text-xs', isDark ? 'text-gray-500' : 'text-gray-500')}>
                    {it.file_type.toUpperCase()} · {fmtSize(it.size)} · {fmtDate(it.uploaded_at)}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Footer */}
      <div className="px-6 py-4 border-t border-border flex justify-end">
        <button
          onClick={async () => {
            setErrorMsg(null);
            setIsCommitting(true);
            try {
              const form = new FormData();
              form.append(
                'collection_name',
                (collectionName && collectionName.length >= 4)
                  ? collectionName
                  : 'Gooclaim Native Upload',
              );
              const resp = await apiClient.postFormData(
                `/uploads/${encodeURIComponent(connectionId)}/commit`,
                form,
              );
              if (!resp.ok) {
                const text = await resp.text();
                throw new Error(`Commit failed (HTTP ${resp.status}): ${text}`);
              }
              setStep('success');
            } catch (err) {
              console.error('NativeUploadView: commit error', err);
              setErrorMsg(err instanceof Error ? err.message : 'Could not commit uploads.');
            } finally {
              setIsCommitting(false);
            }
          }}
          disabled={isCommitting || items.length === 0}
          className={cn(
            'px-4 py-2 rounded-lg text-sm font-medium transition-colors flex items-center gap-2',
            (isCommitting || items.length === 0)
              ? 'bg-sky-600/40 text-white/70 cursor-not-allowed'
              : isDark
                ? 'bg-sky-600 hover:bg-sky-500 text-white'
                : 'bg-sky-600 hover:bg-sky-700 text-white',
          )}
        >
          {isCommitting && <Loader2 className="w-4 h-4 animate-spin" />}
          {isCommitting ? 'Indexing…' : 'Done — Index & Search'}
        </button>
      </div>
    </div>
  );
};
