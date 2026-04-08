import { createApp } from 'vue'
import { createPinia } from 'pinia'
import './assets/styles/foundation.css'
import './assets/styles/layout.css'
import App from './App.vue'
import router from './router'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
