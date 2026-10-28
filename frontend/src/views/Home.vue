<template>
  <div>
    <!-- 还没配好：告诉用户先做什么 -->
    <div v-if="ov && !ov.freshrss" class="guide">
      <h1>{{ t('home.welcome') }}</h1>
      <p class="muted">{{ t('home.needFresh') }}</p>
      <router-link class="btn primary" to="/settings/freshrss">{{ t('home.goFresh') }}</router-link>
    </div>

    <template v-else>
      <p v-if="ov && !ov.channels.length" class="note" role="note">
        <Info :size="16" aria-hidden="true" />{{ t('home.noChannel') }} <router-link to="/settings/channels">{{ t('home.goChannels') }}</router-link></p>
      <p v-if="msg" class="note" :class="msgOk ? 'ok' : 'bad'" role="status">{{ msg }}</p>

      <IssueView v-if="cur" :issue="cur">
        <template #tools>
          <div class="pager" v-if="!previewing">
            <button class="btn ghost sm icon" :disabled="idx >= list.length - 1" @click="go(idx + 1)" :aria-label="t('home.older')" :title="t('home.older')">
              <ChevronLeft :size="18" aria-hidden="true" /></button>
            <select class="input pick" :value="cur.id" @change="open(+$event.target.value)" :aria-label="t('home.pick')">
              <option v-for="x in list" :key="x.id" :value="x.id">{{ md(x.window_end) }} {{ t('kind.' + x.kind) }}（{{ x.total }}）</option>
            </select>
            <button class="btn ghost sm icon" :disabled="idx <= 0" @click="go(idx - 1)" :aria-label="t('home.newer')" :title="t('home.newer')">
              <ChevronRight :size="18" aria-hidden="true" /></button>
          </div>
          <button v-if="previewing" class="btn sm" @click="exitPreview">{{ t('home.exitPreview') }}</button>
          <button class="btn sm" :disabled="busy" @click="preview"><Eye :size="16" aria-hidden="true" />{{ busy === 'preview' ? t('common.loading') : t('home.preview') }}</button>
          <button class="btn sm primary" :disabled="busy || !ov || !ov.channels.length" @click="push">
            <Send :size="16" aria-hidden="true" />{{ busy === 'push' ? t('home.pushing') : t('home.push') }}</button>
        </template>
        <template #status>
          <span v-if="previewing" class="tag warn"><Eye :size="14" aria-hidden="true" />{{ t('home.previewTag') }}</span>
          <template v-else>
            <span v-for="d in cur.deliveries || []" :key="d.channel" class="tag" :class="d.ok ? 'ok' : 'bad'" :title="d.error || ''">
              <Check v-if="d.ok" :size="14" aria-hidden="true" /><X v-else :size="14" aria-hidden="true" />{{ t('nc.types.' + d.channel) }}</span>
          </template>
        </template>
      </IssueView>

      <div v-else-if="loaded" class="guide">
        <h1>{{ t('home.noIssue') }}</h1>
        <p class="muted">{{ t('home.noIssueHint', { m: nextText }) }}</p>
        <div class="acts">
          <button class="btn" :disabled="busy" @click="preview"><Eye :size="16" aria-hidden="true" />{{ busy === 'preview' ? t('common.loading') : t('home.preview') }}</button>
          <button class="btn primary" :disabled="busy || !ov || !ov.channels.length" @click="push"><Send :size="16" aria-hidden="true" />{{ t('home.push') }}</button>
        </div>
      </div>
      <div v-else class="empty">{{ t('common.loading') }}</div>
    </template>
  </div>
</template>

<script setup>
import { Check, ChevronLeft, ChevronRight, Eye, Info, Send, X } from '@lucide/vue'
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import http from '../api.js'
import IssueView from '../components/IssueView.vue'
import { datetime, md } from '../format.js'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const ov = ref(null)
const list = ref([])
const cur = ref(null)
const saved = ref(null)        // 预览前看的那一期，退出预览时回到它
const previewing = ref(false)
const loaded = ref(false)
const busy = ref('')
const msg = ref('')
const msgOk = ref(true)

const idx = computed(() => list.value.findIndex(x => cur.value && x.id === cur.value.id))
const nextText = computed(() => {
  const n = ov.value && Object.values(ov.value.next || {}).filter(Boolean).sort()[0]
  return n ? datetime(n) : t('home.noSchedule')
})

function flash(ok, text) { msgOk.value = ok; msg.value = text }

async function open(id) {
  previewing.value = false
  if (route.params.id !== String(id)) router.replace({ name: 'issue', params: { id } })
  cur.value = await http.get(`/issues/${id}`)
}
function go(i) { if (list.value[i]) open(list.value[i].id) }

async function load() {
  try {
    ;[ov.value, list.value] = await Promise.all([http.get('/overview'), http.get('/issues', { params: { limit: 60 } })])
    const id = route.params.id ? +route.params.id : (list.value.find(x => x.total) || list.value[0] || {}).id
    if (id) cur.value = await http.get(`/issues/${id}`)
  } catch (e) { flash(false, e.message) } finally { loaded.value = true }
}

async function preview() {
  busy.value = 'preview'
  msg.value = ''
  try {
    if (!previewing.value) saved.value = cur.value
    cur.value = await http.post('/issues/preview', { kind: 'manual' }, { timeout: 180000 })
    previewing.value = true
  } catch (e) { flash(false, e.message) } finally { busy.value = '' }
}
function exitPreview() { previewing.value = false; cur.value = saved.value }

async function push() {
  busy.value = 'push'
  msg.value = ''
  try {
    const r = await http.post('/issues/push', { kind: 'manual' }, { timeout: 300000 })
    flash(r.status !== 'failed', r.total ? t('home.pushed.' + r.status, { n: r.total }) : t('home.pushedEmpty'))
    list.value = await http.get('/issues', { params: { limit: 60 } })
    ov.value = await http.get('/overview')
    if (r.total) await open(r.id)
  } catch (e) { flash(false, e.message) } finally { busy.value = '' }
}

watch(() => route.params.id, id => { if (id && (!cur.value || String(cur.value.id) !== id)) open(+id) })
onMounted(load)
</script>

<style scoped>
.guide { max-width: 560px; margin: 48px auto; text-align: center; }
.guide h1 { font-size: 30px; margin: 0 0 8px; }
.guide p { margin: 0 0 20px; line-height: 1.7; }
.acts { display: flex; gap: 10px; justify-content: center; flex-wrap: wrap; }
.note { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin: 0 0 16px; padding: 10px 12px; border-left: 3px solid var(--rule-strong);
  background: var(--wash); font-size: 14px; }
.note.ok { border-left-color: var(--ok); }
.note.bad { border-left-color: var(--bad); color: var(--ink); }
.pager { display: flex; align-items: center; gap: 2px; }
.pick { width: auto; min-height: 34px; padding: 4px 8px; font-size: 13px; max-width: 180px; }
.icon { width: 36px; padding: 0; }
</style>
