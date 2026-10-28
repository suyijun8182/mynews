<template>
  <div class="settings">
    <div class="head"><h1>{{ t('nav.settings') }}</h1></div>
    <div class="layout">
      <nav class="side" :aria-label="t('nav.settings')">
        <router-link v-for="x in TABS" :key="x.id" :to="{ name: 'settings', params: { tab: x.id } }" :class="{ on: tab === x.id }">
          <component :is="x.icon" :size="18" aria-hidden="true" /><span>{{ t('set.tab.' + x.id) }}</span></router-link>
      </nav>

      <section class="pane">
        <!-- FreshRSS -->
        <template v-if="tab === 'freshrss'">
          <h2>{{ t('set.tab.freshrss') }}</h2>
          <FreshForm />
        </template>

        <!-- 分类 -->
        <template v-else-if="tab === 'categories'">
          <h2>{{ t('set.tab.categories') }}</h2>
          <p class="muted lead">{{ t('cat.lead') }}</p>
          <p v-if="catErr" class="err" role="alert">{{ catErr }}</p>
          <div v-else-if="cats === null" class="muted">{{ t('common.loading') }}</div>
          <template v-else>
            <label class="chk all"><input type="checkbox" :checked="allCats" @change="toggleAll($event.target.checked)" />{{ t('cat.all') }}</label>
            <div class="cats">
              <label v-for="c in cats" :key="c" class="chk"><input type="checkbox" :value="c" v-model="picked" :disabled="allCats" />{{ c }}</label>
            </div>
            <div class="acts"><button class="btn primary" :disabled="busy" @click="saveCats">{{ t('common.save') }}</button></div>
          </template>
          <p v-if="okMsg" class="okc small" role="status">{{ okMsg }}</p>
        </template>

        <!-- 早晚报 -->
        <template v-else-if="tab === 'schedule'">
          <h2>{{ t('set.tab.schedule') }}</h2>
          <p class="muted lead">{{ t('sched.lead') }}</p>
          <form v-if="sched" class="form" @submit.prevent="saveSched">
            <div v-for="k in ['morning', 'evening']" :key="k" class="slot">
              <label class="sw-row"><input type="checkbox" v-model="sched[k + '_on']" />{{ t('kind.' + k) }}</label>
              <input class="input time" type="time" v-model="sched[k]" :disabled="!sched[k + '_on']" :aria-label="t('kind.' + k)" required />
              <span class="muted small">{{ t('sched.cover.' + k + (sched.morning_on && sched.evening_on ? '' : '1')) }}</span>
              <span v-if="sched.next && sched.next[k]" class="muted small num">{{ t('sched.next', { t: datetime(sched.next[k]) }) }}</span>
            </div>
            <div class="field narrow">
              <label for="per">{{ t('sched.per') }}</label>
              <input id="per" class="input" type="number" min="1" max="50" v-model.number="sched.per_category" required />
              <small>{{ t('sched.perHint') }}</small>
            </div>
            <p v-if="err" class="err" role="alert">{{ err }}</p>
            <p v-if="okMsg" class="okc small" role="status">{{ okMsg }}</p>
            <div class="acts"><button class="btn primary" :disabled="busy">{{ t('common.save') }}</button></div>
          </form>
        </template>

        <!-- 推送渠道 -->
        <template v-else-if="tab === 'channels'">
          <NotifyChannels />
        </template>

        <!-- AI 摘要 -->
        <template v-else-if="tab === 'ai'">
          <h2>{{ t('set.tab.ai') }}</h2>
          <p class="muted lead">{{ t('ai.lead') }}</p>
          <form v-if="aiCfg" class="form" @submit.prevent="saveAI">
            <label class="sw-row"><input type="checkbox" v-model="aiCfg.enabled" />{{ t('ai.enable') }}</label>
            <div class="presets">
              <span class="muted small">{{ t('ai.presets') }}</span>
              <button v-for="p in PRESETS" :key="p.name" type="button" class="btn sm" @click="preset(p)">{{ p.name }}</button>
            </div>
            <div class="field"><label for="ai-url">{{ t('ai.url') }}</label>
              <input id="ai-url" class="input addr" v-model.trim="aiCfg.base_url" placeholder="https://api.deepseek.com/v1" /></div>
            <div class="two">
              <div class="field"><label for="ai-key">API Key</label>
                <input id="ai-key" class="input" type="password" v-model="aiCfg.api_key" autocomplete="new-password" /></div>
              <div class="field"><label for="ai-model">{{ t('ai.model') }}</label>
                <input id="ai-model" class="input addr" v-model.trim="aiCfg.model" placeholder="deepseek-chat" /></div>
            </div>
            <ol v-if="aiPoints.length" class="points"><li v-for="(p, i) in aiPoints" :key="i">{{ p.text }}</li></ol>
            <p v-if="err" class="err" role="alert">{{ err }}</p>
            <p v-if="okMsg" class="okc small" role="status">{{ okMsg }}</p>
            <div class="acts">
              <button type="button" class="btn" :disabled="!!busy" @click="testAI">{{ busy === 'test' ? t('common.testing') : t('ai.test') }}</button>
              <button class="btn primary" :disabled="!!busy">{{ t('common.save') }}</button>
            </div>
          </form>
        </template>

        <!-- 系统 -->
        <template v-else-if="tab === 'system'">
          <h2>{{ t('set.tab.system') }}</h2>
          <form v-if="site" class="form" @submit.prevent="saveSite">
            <div class="field"><label for="pub">{{ t('sys.public') }}</label>
              <input id="pub" class="input addr" v-model.trim="site.public_url" placeholder="https://news.example.com:8844" />
              <small>{{ t('sys.publicHint') }}</small></div>
            <div class="field narrow"><label for="keep">{{ t('sys.keep') }}</label>
              <input id="keep" class="input" type="number" min="1" max="365" v-model.number="site.retention_days" />
              <small>{{ t('sys.keepHint') }}</small></div>
            <div class="acts"><button class="btn primary" :disabled="!!busy">{{ t('common.save') }}</button></div>
          </form>

          <h3>{{ t('sys.version') }}</h3>
          <div v-if="ver" class="ver">
            <p class="num">{{ t('sys.current', { v: ver.current }) }}<template v-if="ver.latest">　{{ t('sys.latest', { v: ver.latest }) }}</template></p>
            <p v-if="ver.error" class="muted small">{{ t('sys.checkFail', { e: ver.error }) }}</p>
            <template v-if="ver.available">
              <button v-if="ver.supported" class="btn primary" :disabled="!!busy" @click="update">{{ busy === 'update' ? t('sys.updating') : t('sys.update', { v: ver.latest }) }}</button>
              <div v-else class="small">{{ t('sys.dockerHint') }}<pre class="code">docker compose pull && docker compose up -d</pre></div>
            </template>
            <p v-else-if="ver.latest" class="okc small">{{ t('sys.upToDate') }}</p>
          </div>

          <h3>{{ t('sys.password') }}</h3>
          <form class="form narrow-form" @submit.prevent="changePw">
            <div class="field"><label for="opw">{{ t('sys.oldPw') }}</label><input id="opw" class="input" type="password" v-model="pw.old" autocomplete="current-password" required /></div>
            <div class="field"><label for="npw">{{ t('sys.newPw') }}</label><input id="npw" class="input" type="password" v-model="pw.new" minlength="6" autocomplete="new-password" required /></div>
            <div class="acts"><button class="btn" :disabled="!!busy">{{ t('sys.changePw') }}</button></div>
          </form>
          <p v-if="err" class="err" role="alert">{{ err }}</p>
          <p v-if="okMsg" class="okc small" role="status">{{ okMsg }}</p>
        </template>
      </section>
    </div>
  </div>
</template>

<script setup>
import { Bot, Clock, Cog, Rss, Send, Tags } from '@lucide/vue'
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import http, { setAuth } from '../api.js'
import FreshForm from '../components/FreshForm.vue'
import NotifyChannels from '../components/NotifyChannels.vue'
import { datetime } from '../format.js'

const { t } = useI18n()
const route = useRoute()
const TABS = [{ id: 'freshrss', icon: Rss }, { id: 'categories', icon: Tags }, { id: 'schedule', icon: Clock },
  { id: 'channels', icon: Send }, { id: 'ai', icon: Bot }, { id: 'system', icon: Cog }]
// OpenAI 兼容接口的常用预设：只填地址和模型，Key 还要自己填
const PRESETS = [
  { name: 'DeepSeek', base_url: 'https://api.deepseek.com/v1', model: 'deepseek-chat' },
  { name: '通义千问', base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen-plus' },
  { name: 'Kimi', base_url: 'https://api.moonshot.cn/v1', model: 'moonshot-v1-8k' },
  { name: 'Ollama', base_url: 'http://127.0.0.1:11434/v1', model: 'qwen2.5:7b' },
]
const tab = computed(() => (TABS.some(x => x.id === route.params.tab) ? route.params.tab : 'freshrss'))
const busy = ref('')
const err = ref('')
const okMsg = ref('')

// 分类
const fresh = ref(null)
const cats = ref(null)
const catErr = ref('')
const picked = ref([])
const allCats = computed(() => !picked.value.length)
function toggleAll(on) { picked.value = on ? [] : [...(cats.value || [])] }
async function loadCats() {
  cats.value = null
  catErr.value = ''
  try {
    fresh.value = await http.get('/settings/freshrss')
    if (!fresh.value.url) { catErr.value = t('cat.needFresh'); return }
    const r = await http.post('/settings/freshrss/test', fresh.value, { timeout: 60000 })
    cats.value = [...r.categories, t('cat.uncat')]
    // 后端用「未分类」表示没有分类的订阅源，英文界面显示成 Uncategorized
    picked.value = (fresh.value.categories || []).map(c => (c === '未分类' ? t('cat.uncat') : c)).filter(c => cats.value.includes(c))
  } catch (e) { catErr.value = e.message }
}
async function saveCats() {
  await run(async () => {
    await http.put('/settings/freshrss', { ...fresh.value, categories: picked.value.map(c => (c === t('cat.uncat') ? '未分类' : c)) })
  })
}

// 早晚报
const sched = ref(null)
async function saveSched() { await run(async () => { sched.value = await http.put('/settings/schedule', sched.value) }) }

// AI
const aiCfg = ref(null)
const aiPoints = ref([])
function preset(p) { Object.assign(aiCfg.value, { base_url: p.base_url, model: p.model }) }
async function saveAI() { await run(async () => { aiCfg.value = await http.put('/settings/ai', aiCfg.value) }) }
async function testAI() {
  aiPoints.value = []
  await run(async () => { aiPoints.value = (await http.post('/settings/ai/test', aiCfg.value, { timeout: 120000 })).points }, 'test', t('ai.testOk'))
}

// 系统
const site = ref(null)
const ver = ref(null)
const pw = reactive({ old: '', new: '' })
async function saveSite() { await run(async () => { site.value = await http.put('/settings/site', site.value) }) }
async function update() {
  await run(async () => { okMsg.value = (await http.post('/system/update', null, { timeout: 300000 })).message }, 'update', null)
}
async function changePw() {
  await run(async () => {
    const r = await http.post('/auth/password', { old_password: pw.old, new_password: pw.new })
    setAuth(r.token, r.username)
    pw.old = pw.new = ''
  }, 'pw', t('sys.pwChanged'))
}

async function run(fn, kind = 'save', done = t('common.saved')) {
  err.value = okMsg.value = ''
  busy.value = kind
  try { await fn(); if (done) okMsg.value = done } catch (e) { err.value = e.message } finally { busy.value = '' }
}

async function loadTab(x) {
  err.value = okMsg.value = ''
  try {
    if (x === 'categories') await loadCats()
    else if (x === 'schedule') sched.value = await http.get('/settings/schedule')
    else if (x === 'ai') aiCfg.value = await http.get('/settings/ai')
    else if (x === 'system') {
      site.value = await http.get('/settings/site')
      ver.value = await http.get('/system/version')
    }
  } catch (e) { err.value = e.message }
}
watch(tab, loadTab, { immediate: true })
</script>

<style scoped>
.head { border-bottom: 3px solid var(--rule-strong); margin-bottom: 24px; }
.head h1 { margin: 0 0 8px; font-size: 30px; }
.layout { display: grid; grid-template-columns: 200px minmax(0, 1fr); gap: 40px; }
.side { display: flex; flex-direction: column; gap: 2px; }
.side a { display: flex; align-items: center; gap: 10px; min-height: 44px; padding: 0 12px; color: var(--muted); border-left: 2px solid transparent; }
.side a:hover { color: var(--ink); background: var(--wash); text-decoration: none; }
.side a.on { color: var(--ink); font-weight: 600; border-left-color: var(--brand); }
.pane { min-width: 0; max-width: 760px; }
.pane h2 { margin: 0 0 6px; font-size: 22px; }
.pane h3 { margin: 32px 0 10px; font-size: 18px; padding-top: 20px; border-top: 1px solid var(--rule); }
.lead { margin: 0 0 18px; font-size: 14.5px; line-height: 1.7; }
.form { display: flex; flex-direction: column; gap: 16px; margin-top: 12px; }
.narrow { max-width: 220px; }
.narrow-form { max-width: 360px; }
.two { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.acts { display: flex; gap: 10px; flex-wrap: wrap; }
.slot { display: flex; align-items: center; gap: 12px 16px; flex-wrap: wrap; padding: 10px 0; border-bottom: 1px solid var(--rule); }
.sw-row, .chk { display: inline-flex; align-items: center; gap: 8px; min-height: 40px; cursor: pointer; font-size: 15px; }
.sw-row { min-width: 90px; font-weight: 600; }
.sw-row input, .chk input { width: 18px; height: 18px; accent-color: var(--ink); }
.time { width: 130px; }
.cats { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 0 16px; margin: 4px 0 16px; padding: 8px 0;
  border-top: 1px solid var(--rule); border-bottom: 1px solid var(--rule); }
.all { font-weight: 600; }
.presets { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.points { margin: 0; padding: 10px 10px 10px 32px; background: var(--wash); font-size: 14.5px; }
.ver p { margin: 0 0 8px; }
.code { margin: 8px 0 0; padding: 10px 12px; background: var(--wash); font: 13px var(--mono); overflow-x: auto; }
p { margin: 0; }
@media (max-width: 760px) {
  .layout { grid-template-columns: minmax(0, 1fr); gap: 16px; }
  /* grid 子项默认 min-width: auto，不设 0 的话一排标签会把整页撑宽 */
  .side { flex-direction: row; overflow-x: auto; min-width: 0; border-bottom: 1px solid var(--rule); }
  .side a { border-left: 0; border-bottom: 2px solid transparent; white-space: nowrap; }
  .side a.on { border-bottom-color: var(--brand); }
  .two { grid-template-columns: minmax(0, 1fr); }
}
</style>
