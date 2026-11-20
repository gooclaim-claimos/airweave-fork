/**
 * DocumentProductLabel — Gooclaim (T531): which insurance product a document covers.
 *
 * A member's answer must come from THEIR policy's wording. At upload the product number
 * (IRDAI UIN) printed on the first pages is read as a suggestion; here the tenant confirms
 * it, types another, or marks the document as applying to every member. Only a confirmed
 * label decides which members' questions this document answers.
 */

import React, { useState } from 'react';
import { Check, Loader2 } from 'lucide-react';

import { apiClient } from '@/lib/api';
import { cn } from '@/lib/utils';

export interface LabelledUpload {
  upload_id: string;
  detected_uins?: string[];
  product_uins?: string[];
  applies_to?: 'products' | 'general' | null;
}

interface Props<T extends LabelledUpload> {
  item: T;
  connectionId: string;
  isDark: boolean;
  onSaved: (item: T) => void;
}

const UIN_PATTERN = /^[A-Z]{5,9}\d{5}V\d{6}$/;

export function DocumentProductLabel<T extends LabelledUpload>({
  item,
  connectionId,
  isDark,
  onSaved,
}: Props<T>) {
  const [editing, setEditing] = useState(false);
  const [typed, setTyped] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const detected = item.detected_uins ?? [];
  const confirmed = item.applies_to ?? null;

  const save = async (body: { product_uins: string[]; applies_to: 'products' | 'general' }) => {
    setError(null);
    setSaving(true);
    try {
      const resp = await apiClient.put(
        `/uploads/${encodeURIComponent(connectionId)}/${encodeURIComponent(item.upload_id)}/labels`,
        undefined,
        body,
      );
      if (!resp.ok) throw new Error(`Could not save (HTTP ${resp.status})`);
      onSaved({ ...item, ...(await resp.json()) });
      setEditing(false);
      setTyped('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save.');
    } finally {
      setSaving(false);
    }
  };

  const muted = isDark ? 'text-gray-400' : 'text-gray-500';
  const button = cn(
    'text-xs px-2 py-0.5 rounded border transition-colors disabled:opacity-50',
    isDark ? 'border-gray-700 hover:bg-gray-800' : 'border-gray-300 hover:bg-gray-100',
  );

  if (confirmed && !editing) {
    return (
      <div className={cn('flex items-center gap-2 text-xs mt-1', muted)}>
        <Check className="w-3.5 h-3.5 text-emerald-600" />
        <span>
          {confirmed === 'general'
            ? 'Answers every member'
            : `Answers members of product ${(item.product_uins ?? []).join(', ')}`}
        </span>
        <button type="button" className={button} onClick={() => setEditing(true)}>
          Change
        </button>
      </div>
    );
  }

  const typedUin = typed.replace(/\s+/g, '').toUpperCase();
  return (
    <div className="mt-1 space-y-1">
      <div className={cn('flex flex-wrap items-center gap-2 text-xs', muted)}>
        {detected.length > 0 ? (
          <>
            <span>Product number found in the document: {detected.join(', ')}</span>
            <button
              type="button"
              className={button}
              disabled={saving}
              onClick={() => save({ product_uins: detected, applies_to: 'products' })}
            >
              Confirm
            </button>
          </>
        ) : (
          <span>No product number found in the document.</span>
        )}
        <button
          type="button"
          className={button}
          disabled={saving}
          onClick={() => save({ product_uins: [], applies_to: 'general' })}
        >
          Answers every member
        </button>
        {saving && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
      </div>
      <div className="flex items-center gap-2">
        <input
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          placeholder="Or type the product UIN"
          aria-label="Product UIN"
          className={cn(
            'text-xs px-2 py-1 rounded border w-56 bg-transparent',
            isDark ? 'border-gray-700' : 'border-gray-300',
          )}
        />
        <button
          type="button"
          className={button}
          disabled={saving || !UIN_PATTERN.test(typedUin)}
          onClick={() => save({ product_uins: [typedUin], applies_to: 'products' })}
        >
          Save
        </button>
      </div>
      {error && <div className="text-xs text-red-600 dark:text-red-400">{error}</div>}
    </div>
  );
}
