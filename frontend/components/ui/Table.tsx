import { ReactNode } from 'react'

export interface TableProps {
  headers: string[]
  rows: (string | ReactNode)[][]
  emptyMessage?: string
}

export function Table({ headers, rows, emptyMessage = 'No data available.' }: TableProps) {
  return (
    <div className="overflow-x-auto rounded-lg border border-gray-800">
      <table className="min-w-full divide-y divide-gray-800 text-sm">
        <thead className="bg-gray-900">
          <tr>
            {headers.map((header) => (
              <th
                key={header}
                className="px-4 py-2 text-left font-medium text-gray-400"
              >
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-800 bg-gray-950">
          {rows.length === 0 ? (
            <tr>
              <td colSpan={headers.length} className="px-4 py-6 text-center text-gray-500">
                {emptyMessage}
              </td>
            </tr>
          ) : (
            rows.map((row, i) => (
              <tr key={i} className="hover:bg-gray-900/50">
                {row.map((cell, j) => (
                  <td key={j} className="px-4 py-2 text-gray-200">
                    {cell}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  )
}
