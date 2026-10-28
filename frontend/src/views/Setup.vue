<template>
  <div class="auth">
    <div class="box" :class="{ wide: step === 'channels' }">
      <h1>{{ t('app.name') }}</h1>
      <ol class="steps" :aria-label="t('setup.steps')">
        <li v-for="(s, i) in steps" :key="s" :class="{ on: s === step, done: steps.indexOf(step) > i }">{{ t('setup.step.' + s) }}</li>
      </ol>

      <!-- 已有数据库配置但暂时连不上：不让用户重填，自动重试 -->
      <template v-if="step === 'wait'">
        <h2>{{ t('setup.waitTitle') }}</h2>
        <p class="muted">{{ t('setup.waitText') }}</p>
        <p v-if="err" class="err">{{ err }}</p>
        <button class="btn" @click="poll">{{ t('setup.retry') }}</button>
      </template>

      <!-- 1. 数据库（只有 Docker 部署有这一步；Linux 一键安装用 SQLite，跳过） -->
      <form v-else-if="step === 'db'" class="form" @submit.prevent="saveDb">
        <h2>{{ t('setup.dbTitle') }}</h2>
        <p class="muted intro">{{ t('setup.dbIntro') }}</p>
        <div class="row">
          <div class="field grow"><label for="dh">{{ t('setup.host') }}</label><input id="dh" class="input" v-model.trim="db.host" placeholder="192.168.1.10" required /></div>
          <div class="field port"><label for="dp">{{ t('setup.port') }}</label><input id="dp" class="input" type="number" v-model.number="db.port" min="1" max="65535" required /></div>
        </div>
        <div class="field"><label for="du">{{ t('setup.user') }}</label><input id="du" class="input" v-model.trim="db.user" autocomplete="off" required /></div>
        <div class="field"><label for="dpw">{{ t('setup.password') }}</label><input id="dpw" class="input" type="password" v-model="db.password" autocomplete="new-password" /></div>
        <div class="field"><label for="dn">{{ t('setup.database') }}</label><input id="dn" class="input" v-model.trim="db.database" required />
          <small>{{ t('setup.hostHint') }}</small></div>
        <div v-if="needCode" class="field"><label for="dc">{{ t('setup.code') }}</label><input id="dc" class="input addr" v-model.trim="code" autocomplete="off" />
          <small>{{ t('setup.codeHint') }}</small></div>
        <p v-if="okMsg" class="okc small">{{ okMsg }}</p>
        <p v-if="err" class="err" role="alert">{{ err }}</p>
        <div class="acts">
          <button type="button" class="btn" :disabled="!!busy" @click="testDb">{{ busy === 'test' ? t('common.testing') : t('setup.test') }}</button>
          <button class="btn primary" :disabled="!!busy">{{ busy === 'save' ? t('common.saving') : t('setup.next') }}</button>
        </div>
        <details class="sql">
          <summary>{{ t('setup.sqlTitle') }}</summary>
          <pre class="code">{{ sql }}</pre>
        </details>
      </form>

      <!-- 2. 管理员 -->
      <form v-else-if="step === 'admin'" class="form" @submit.prevent="saveAdmin">
        <h2>{{ t('setup.adminTitle') }}</h2>
        <p class="muted intro">{{ t('setup.adminIntro') }}</p>
        <div class="field"><label for="au">{{ t('login.user') }}</label><input id="au" class="input" v-model.trim="admin.username" autocomplete="username" required /></div>
        <div class="field"><label for="ap">{{ t('login.pw') }}</label><input id="ap" class="input" type="password" v-model="admin.password" minlength="6" autocomplete="new-password" required />
          <small>{{ t('setup.pwHint') }}</small></div>
        <div v-if="needCode" class="field"><label for="ac">{{ t('setup.code') }}</label><input id="ac" class="input addr" v-model.trim="code" autocomplete="off" />
          <small>{{ t('setup.codeHint') }}</small></div>
        <p v-if="err" class="err" role="alert">{{ err }}</p>
        <div class="acts"><button class="btn primary" :disabled="!!busy">{{ t('setup.next') }}</button></div>
      </form>

      <!-- 3. FreshRSS -->
      <template v-else-if="step === 'fresh'">
        <h2>{{ t('setup.freshTitle') }}</h2>
        <FreshForm :save-text="t('setup.next')" @saved="step = 'channels'" />
        <div class="skip"><button class="btn ghost sm" @click="step = 'channels'">{{ t('setup.later') }}</button></div>
      </template>

      <!-- 4. 推送渠道（可跳过） -->
      <template v-else-if="step === 'channels'">
        <p class="muted intro">{{ t('setup.channelsIntro') }}</p>
        <NotifyChannels />
        <div class="acts end">
          <button class="btn ghost" @click="finish">{{ t('setup.skip') }}</button>
          <button class="btn primary" @click="finish">{{ t('setup.done') }}</button>
        </div>
      </template>
      <div v-else class="muted">{{ t('common.loading') }}</div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import http, { auth, checkSetup, setAuth, setupState } from '../api.js'
import FreshForm from '../components/FreshForm.vue'
import NotifyChannels from '../components/NotifyChannels.vue'

const { t } = useI18n()
const router = useRouter()
const step = ref('')
const needDb = ref(false)   // 这次安装要不要填数据库（决定步骤条有几步）
const db = reactive({ host: '', port: 3306, user: 'mynews', password: '', database: 'mynews' })
const admin = reactive({ username: 'admin', password: '' })
const busy = ref('')
const err = ref('')
const okMsg = ref('')
const needCode = ref(false)
const code = ref('')
let timer = null

const steps = computed(() => (needDb.value ? ['db', 'admin', 'fresh', 'channels'] : ['admin', 'fresh', 'channels']))
const sql = computed(() => `CREATE DATABASE ${db.database || 'mynews'} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER '${db.user || 'mynews'}'@'%' IDENTIFIED BY 'your-password';
GRANT ALL PRIVILEGES ON ${db.database || 'mynews'}.* TO '${db.user || 'mynews'}'@'%';
FLUSH PRIVILEGES;`)
const opt = () => ({ timeout: 60000, headers: code.value ? { 'X-Setup-Code': code.value } : {} })
function showErr(e) {
  if (e.message === 'setup_code_required') { needCode.value = true; err.value = t('setup.codeNeeded') } else err.value = e.message
}

async function poll() {
  err.value = ''
  try {
    await checkSetup()
    if (!setupState.configured) {
      needDb.value = true
      step.value = setupState.present ? 'wait' : 'db'
      if (setupState.present && !timer) timer = setInterval(poll, 5000)
      return
    }
    clearInterval(timer)
    timer = null
    const s = await http.get('/auth/status')
    if (!s.initialized) step.value = 'admin'
    else if (auth.token) step.value = step.value === 'channels' ? 'channels' : 'fresh'
    else router.replace({ name: 'login' })
  } catch (e) { err.value = e.message }
}
onMounted(poll)
onUnmounted(() => clearInterval(timer))

async function testDb() {
  err.value = okMsg.value = ''
  busy.value = 'test'
  try { okMsg.value = (await http.post('/setup/test', db, opt())).message } catch (e) { showErr(e) } finally { busy.value = '' }
}
async function saveDb() {
  err.value = okMsg.value = ''
  busy.value = 'save'
  try {
    await http.post('/setup/save', db, opt())
    Object.assign(setupState, { configured: true, present: true })
    step.value = 'admin'
  } catch (e) { showErr(e) } finally { busy.value = '' }
}
async function saveAdmin() {
  err.value = ''
  busy.value = 'save'
  try {
    const r = await http.post('/auth/setup', admin, opt())
    setAuth(r.token, r.username)
    step.value = 'fresh'
  } catch (e) { showErr(e) } finally { busy.value = '' }
}
function finish() { router.replace('/') }
</script>

<style scoped>
.auth { min-height: 100vh; display: flex; justify-content: center; padding: 48px 16px; }
.box { width: 100%; max-width: 520px; display: flex; flex-direction: column; gap: 16px; }
.box.wide { max-width: 860px; }
h1 { margin: 0; font: 700 40px/1.1 var(--serif); color: var(--brand); border-bottom: 3px solid var(--rule-strong); padding-bottom: 12px; }
h2 { margin: 0; font-size: 22px; }
.intro { margin: -6px 0 0; font-size: 14.5px; line-height: 1.7; }
.form { display: flex; flex-direction: column; gap: 16px; }
.row { display: flex; gap: 12px; }
.grow { flex: 1; min-width: 0; }
.port { width: 110px; flex: none; }
.acts { display: flex; gap: 10px; justify-content: flex-end; flex-wrap: wrap; }
.skip { display: flex; justify-content: flex-start; margin-top: -8px; }
.steps { list-style: none; margin: 0; padding: 0; display: flex; gap: 8px; counter-reset: s; }
.steps li { flex: 1; font-size: 13px; color: var(--muted); padding-top: 8px; border-top: 2px solid var(--rule); counter-increment: s; }
.steps li::before { content: counter(s) ". "; }
.steps li.on { color: var(--ink); font-weight: 600; border-top-color: var(--brand); }
.steps li.done { color: var(--ink); border-top-color: var(--rule-strong); }
.sql { font-size: 14px; }
.sql summary { cursor: pointer; color: var(--link); min-height: 32px; display: flex; align-items: center; }
.code { margin: 8px 0 0; padding: 10px 12px; background: var(--wash); font: 12px/1.6 var(--mono); overflow-x: auto; white-space: pre; }
p { margin: 0; }
</style>
