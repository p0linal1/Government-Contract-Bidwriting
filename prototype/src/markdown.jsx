// Just enough markdown for the Drafter's proposals and the team's fact files: headings, paragraphs,
// lists, checklists, tables, rules, bold, italics, and code. Rendering it as React elements keeps every word escaped. The blanks the
// Drafter leaves for Doug are marked so they stand out.

const NEEDED = /(\[NEEDED FROM DOUG[^\]]*\])/
// A checklist item, as the context tracker writes them: "- [x] done" or "- [ ] not yet".
const TASK = /^\[([ xX])\]\s+(.*)/
const EMPHASIS = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*)/

function emphasis(text, keyPrefix) {
  return text.split(EMPHASIS).map((part, i) => {
    const key = `${keyPrefix}-${i}`
    if (part.startsWith('**') && part.endsWith('**') && part.length > 4) return <strong key={key}>{part.slice(2, -2)}</strong>
    if (part.startsWith('`') && part.endsWith('`') && part.length > 2) return <code key={key}>{part.slice(1, -1)}</code>
    if (part.startsWith('*') && part.endsWith('*') && part.length > 2) return <em key={key}>{part.slice(1, -1)}</em>
    return part
  })
}

function inline(text) {
  return text.split(NEEDED).map((part, i) =>
    NEEDED.test(part) ? (
      <mark className="bid-needed" key={i}>
        {part}
      </mark>
    ) : (
      emphasis(part, i)
    ),
  )
}

const cells = (row) =>
  row
    .trim()
    .replace(/^\||\|$/g, '')
    .split('|')
    .map((cell) => cell.trim())

const isTableRule = (row) => /^\|?[\s:|-]+\|?$/.test(row.trim()) && row.includes('-')

function Table({ rows }) {
  const [head, ...body] = rows.filter((row) => !isTableRule(row)).map(cells)
  return (
    <table>
      <thead>
        <tr>
          {head.map((cell, i) => (
            <th key={i}>{inline(cell)}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {body.map((row, r) => (
          <tr key={r}>
            {row.map((cell, i) => (
              <td key={i}>{inline(cell)}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

// Groups the lines into blocks: a heading, a rule, a run of list items, a run of table rows, or a paragraph.
function blocks(markdown) {
  const found = []
  let paragraph = []
  const endParagraph = () => {
    if (paragraph.length) found.push({ kind: 'p', text: paragraph.join(' ') })
    paragraph = []
  }
  for (const line of markdown.split('\n')) {
    const heading = line.match(/^(#{1,6})\s+(.*)/)
    const item = line.match(/^\s*([-*+]|\d+[.)])\s+(.*)/)
    const last = found.at(-1)
    if (!line.trim()) endParagraph()
    else if (heading) {
      endParagraph()
      found.push({ kind: 'h', level: heading[1].length, text: heading[2] })
    } else if (/^\s*(-{3,}|\*{3,})\s*$/.test(line)) {
      endParagraph()
      found.push({ kind: 'hr' })
    } else if (line.trim().startsWith('|')) {
      endParagraph()
      if (last?.kind === 'table' && !paragraph.length) last.rows.push(line)
      else found.push({ kind: 'table', rows: [line] })
    } else if (item) {
      endParagraph()
      const ordered = /\d/.test(item[1])
      if (last?.kind === 'list' && last.ordered === ordered) last.items.push(item[2])
      else found.push({ kind: 'list', ordered, start: ordered ? parseInt(item[1], 10) : undefined, items: [item[2]] })
    } else paragraph.push(line.trim())
  }
  endParagraph()
  return found
}

export function Markdown({ text }) {
  return blocks(text).map((block, i) => {
    if (block.kind === 'h') {
      const Heading = `h${Math.min(block.level, 4)}`
      return <Heading key={i}>{inline(block.text)}</Heading>
    }
    if (block.kind === 'hr') return <hr key={i} />
    if (block.kind === 'table') return <Table key={i} rows={block.rows} />
    if (block.kind === 'list') {
      const List = block.ordered ? 'ol' : 'ul'
      return (
        <List key={i} start={block.start}>
          {block.items.map((item, j) => {
            const task = item.match(TASK)
            if (!task) return <li key={j}>{inline(item)}</li>
            const done = task[1] !== ' '
            return (
              <li key={j} className={`md-task ${done ? 'is-done' : ''}`}>
                <span className="md-box" role="img" aria-label={done ? 'Done' : 'Not done'} />
                <span>{inline(task[2])}</span>
              </li>
            )
          })}
        </List>
      )
    }
    return <p key={i}>{inline(block.text)}</p>
  })
}
