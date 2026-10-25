// A plain spreadsheet grid: sticky header, numbered rows, and a sticky first column on phones.
export function Sheet({ columns, rows, rowKey, onRowClick, numbered = true, label }) {
  return (
    <div className="sheet-wrap">
      <table className={`sheet ${onRowClick ? 'sheet-clickable' : ''}`} aria-label={label}>
        <thead>
          <tr>
            {numbered && <th className="sheet-num" aria-hidden="true" />}
            {columns.map((column) => (
              <th key={column.key} className={column.align === 'right' ? 'right' : ''} style={column.width ? { width: column.width } : undefined}>
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr
              key={rowKey ? rowKey(row) : i}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              tabIndex={onRowClick ? 0 : undefined}
              onKeyDown={onRowClick ? (event) => event.key === 'Enter' && onRowClick(row) : undefined}
            >
              {numbered && <td className="sheet-num">{i + 1}</td>}
              {columns.map((column) => (
                <td key={column.key} className={column.align === 'right' ? 'right' : ''}>
                  {column.render ? column.render(row) : row[column.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function Status({ tone, children }) {
  return <span className={`cell-status cell-${tone}`}>{children}</span>
}
