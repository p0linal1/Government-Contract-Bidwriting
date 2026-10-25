// Folds the Vite build in dist/ into one self-contained click-through.html.
// Browsers refuse to load module scripts from separate files over file://,
// so the page only opens with a double-click when everything is inline.
import { readFileSync, readdirSync, writeFileSync } from 'node:fs'

const dist = new URL('../dist/', import.meta.url)
const read = (name) => readFileSync(new URL(name, dist), 'utf8')

const assets = readdirSync(new URL('assets/', dist))
const script = assets.find((name) => name.endsWith('.js'))
const stylesheet = assets.find((name) => name.endsWith('.css'))
const favicon = Buffer.from(read('favicon.svg')).toString('base64')

// An inline script ends at the first "</script", even inside a string.
const code = read(`assets/${script}`).replaceAll('</script', '<\\/script')
const css = read(`assets/${stylesheet}`)

const page = read('index.html')
  .replace(/<script type="module" crossorigin src="[^"]+"><\/script>/, () => `<script type="module">\n${code}\n</script>`)
  .replace(/<link rel="stylesheet" crossorigin href="[^"]+">/, () => `<style>\n${css}\n</style>`)
  .replace('href="./favicon.svg"', () => `href="data:image/svg+xml;base64,${favicon}"`)

if (page.includes('./assets/')) {
  throw new Error('An asset was left unlinked. Check the patterns against dist/index.html.')
}

writeFileSync(new URL('../click-through.html', import.meta.url), page)
