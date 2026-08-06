import { createApp } from 'vue'
import ArcoVue from '@arco-design/web-vue'
import '@arco-design/web-vue/dist/arco.css'
import './styles/theme.css'
import { i18n } from './i18n'
import App from './App.vue'

const app = createApp(App)
app.use(ArcoVue)
app.use(i18n)
app.mount('#app')

// 注册 Service Worker (生产环境 + http/https协议下)
if (typeof window !== 'undefined' &&
    'serviceWorker' in navigator &&
    /^https?:/.test(window.location.protocol)) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('./sw.js').catch((err) => {
      console.warn('[PWA] SW registration failed:', err)
    })
  })
}
