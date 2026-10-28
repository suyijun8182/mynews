import { createApp } from 'vue'
import '@fontsource/newsreader/latin-400.css'
import '@fontsource/newsreader/latin-600.css'
import '@fontsource/newsreader/latin-700.css'
import App from './App.vue'
import router from './router.js'
import { i18n } from './i18n/index.js'
import './style.css'

createApp(App).use(router).use(i18n).mount('#app')
