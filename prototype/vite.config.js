import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// host: true lets phones on the same Wi-Fi open the dev server.
export default defineConfig({
  plugins: [react()],
  server: { host: true, port: 5180 },
})
