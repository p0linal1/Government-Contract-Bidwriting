// The tool calls behind each research step, written the way a Managed Agents session reports
// them: the built-in tools (web_search, web_fetch, read, grep, bash, write), the Google Drive
// MCP connector for Cadocary's files, and plain agent messages. `result` is the text the tool
// returned. `seconds` is how long the call took in a real run, used for the timestamps.

export const UPLOADS = '/mnt/session/uploads'
export const OUTPUTS = '/mnt/session/outputs'

export const search = (query, results, seconds = 3) => ({
  name: 'web_search',
  input: { query },
  result: results.map(([title, url]) => ({ type: 'search_result', title, url })),
  seconds,
})

export const fetchPage = (url, result, seconds = 5) => ({ name: 'web_fetch', input: { url }, result, seconds })

export const read = (file, result, seconds = 4) => ({ name: 'read', input: { file_path: file.startsWith('/') ? file : `${UPLOADS}/${file}` }, result, seconds })

export const grep = (pattern, file, result, seconds = 1) => ({ name: 'grep', input: { pattern, path: `${UPLOADS}/${file}` }, result, seconds })

export const bash = (command, result, seconds = 3) => ({ name: 'bash', input: { command }, result, seconds })

export const write = (file, result, seconds = 2) => ({ name: 'write', input: { file_path: `${OUTPUTS}/${file}` }, result, seconds })

export const driveSearch = (query, result, seconds = 2) => ({ mcp: 'google_drive', name: 'search_files', input: { query }, result, seconds })

export const driveRead = (fileName, result, seconds = 3) => ({ mcp: 'google_drive', name: 'read_file', input: { name: fileName }, result, seconds })

export const note = (text, seconds = 6) => ({ message: text, seconds })
