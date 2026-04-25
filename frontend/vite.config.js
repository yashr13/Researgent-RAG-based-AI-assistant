import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/health': 'http://localhost:8000',
      '/upload': 'http://localhost:8000',
      '/query': 'http://localhost:8000',
      '/projects': 'http://localhost:8000',
      '/documents': 'http://localhost:8000',
      '/chats': 'http://localhost:8000',
      '/messages': 'http://localhost:8000',
      '/arxiv': 'http://localhost:8000'
    }
  }
})
