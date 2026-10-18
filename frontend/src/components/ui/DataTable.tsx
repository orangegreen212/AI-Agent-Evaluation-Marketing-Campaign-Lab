import type { ReactNode, ThHTMLAttributes, TdHTMLAttributes } from 'react';
import { clsx } from '@/lib/utils';

interface Column<T> {
  key: string;
  header: string;
  className?: string;
  render: (row: T) => ReactNode;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  empty?: ReactNode;
  dense?: boolean;
}

export function DataTable<T>({ columns, rows, rowKey, empty, dense }: DataTableProps<T>) {
  if (rows.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-surface-700 bg-surface-900/40 px-4 py-10 text-center text-sm text-ink-400">
        {empty ?? 'No rows to display.'}
      </div>
    );
  }
  return (
    <div className="overflow-x-auto rounded-lg border border-surface-700/70">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="bg-surface-800/80">
            {columns.map((c) => (
              <th
                key={c.key}
                className={clsx(
                  'border-b border-surface-700/70 px-4 py-2.5 text-left text-2xs font-semibold uppercase tracking-wider text-ink-400',
                  c.className,
                )}
              >
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr
              key={rowKey(row)}
              className={clsx(
                'border-b border-surface-800/60 transition-colors hover:bg-surface-800/40',
                i % 2 === 1 && 'bg-surface-900/30',
                dense && 'text-xs',
              )}
            >
              {columns.map((c) => (
                <td
                  key={c.key}
                  className={clsx(
                    'px-4 py-2.5 align-middle text-ink-200',
                    c.className,
                    dense && 'py-2',
                  )}
                >
                  {c.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export type { Column };
export type { ThHTMLAttributes, TdHTMLAttributes };
