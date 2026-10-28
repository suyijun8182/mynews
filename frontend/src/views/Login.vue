<template>
  <div class="auth">
    <form class="box" @submit.prevent="login">
      <h1>{{ t('app.name') }}</h1>
      <p class="muted sub">{{ t('login.sub') }}</p>
      <div class="field"><label for="lu">{{ t('login.user') }}</label><input id="lu" class="input" v-model.trim="f.username" autocomplete="username" required /></div>
      <div class="field"><label for="lp">{{ t('login.pw') }}</label><input id="lp" class="input" type="password" v-model="f.password" autocomplete="current-password" required /></div>
      <p v-if="err" class="err" role="alert">{{ err }}</p>
      <button class="btn primary full" :disabled="busy">{{ busy ? t('common.loading') : t('login.go') }}</button>
    </form>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import http, { setAuth } from '../api.js'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const f = reactive({ username: 'admin', password: '' })
const err = ref('')
const busy = ref(false)

// 还没有管理员：去安装向导
onMounted(async () => {
  try { if (!(await http.get('/auth/status')).initialized) router.replace({ name: 'setup' }) } catch (e) { /* 由拦截器处理 */ }
})

async function login() {
  err.value = ''
  busy.value = true
  try {
    const r = await http.post('/auth/login', f)
    setAuth(r.token, r.username)
    const next = typeof route.query.next === 'string' && route.query.next.startsWith('/') ? route.query.next : '/'
    router.replace(next)
  } catch (e) { err.value = e.message } finally { busy.value = false }
}
</script>

<style scoped>
.auth { min-height: 100vh; display: grid; place-items: center; padding: 24px 16px; }
.box { width: 100%; max-width: 380px; display: flex; flex-direction: column; gap: 16px; border-top: 3px solid var(--rule-strong); padding-top: 20px; }
h1 { margin: 0; font: 700 44px/1.1 var(--serif); color: var(--brand); }
.sub { margin: -8px 0 4px; font-size: 14.5px; }
.full { width: 100%; }
p { margin: 0; }
</style>
