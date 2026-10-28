<template>
  <div>
    <div class="head"><h1>{{ t('history.title') }}</h1><span class="muted small">{{ t('history.hint', { n: days }) }}</span></div>
    <p v-if="msg" class="small" :class="msgOk ? 'okc' : 'err'" role="status">{{ msg }}</p>
    <div class="tbl-wrap" v-if="rows.length">
      <table class="tbl">
        <thead><tr><th>{{ t('history.issue') }}</th><th>{{ t('history.window') }}</th><th class="r">{{ t('history.count') }}</th>
          <th>{{ t('history.channels') }}</th><th /></tr></thead>
        <tbody>
          <tr v-for="r in rows" :key="r.id">
            <td><router-link :to="{ name: 'issue', params: { id: r.id } }" class="kind">{{ md(r.window_end) }} {{ t('kind.' + r.kind) }}</router-link></td>
            <td class="num muted">{{ span(r.window_start, r.window_end) }}</td>
            <td class="r num">{{ r.total }}</td>
            <td>
              <span v-if="r.status === 'empty'" class="muted small">{{ t('history.empty') }}</span>
              <span v-else-if="!r.deliveries.length" class="muted small">{{ t('history.noChannel') }}</span>
              <span v-for="d in r.deliveries" :key="d.channel" class="tag" :class="d.ok ? 'ok' : 'bad'" :title="d.error || ''">
                <Check v-if="d.ok" :size="14" aria-hidden="true" /><X v-else :size="14" aria-hidden="true" />{{ t('nc.types.' + d.channel) }}</span>
              <div v-for="d in r.deliveries.filter(x => !x.ok)" :key="'e' + d.channel" class="err small">{{ t('nc.types.' + d.channel) }}：{{ d.error }}</div>
            </td>
            <td class="r">
              <button v-if="r.total" class="btn sm" :disabled="busy === r.id" @click="repush(r)">
                <RotateCw :size="14" aria-hidden="true" />{{ busy === r.id ? t('home.pushing') : (r.status === 'sent' ? t('history.again') : t('history.retry')) }}</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-else-if="loaded" class="empty">{{ t('history.none') }}</div>
    <div v-else class="empty">{{ t('common.loading') }}</div>
  </div>
</template>

<script setup>
import { Check, RotateCw, X } from '@lucide/vue'
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import http from '../api.js'
import { md, span } from '../format.js'

const { t } = useI18n()
const rows = ref([])
const loaded = ref(false)
const busy = ref(0)
const msg = ref('')
const msgOk = ref(true)
const days = ref(10)

async function load() {
  try {
    rows.value = await http.get('/issues', { params: { limit: 200 } })
    days.value = (await http.get('/settings/site')).retention_days
  } catch (e) { msgOk.value = false; msg.value = e.message } finally { loaded.value = true }
}

// 有失败的渠道：只重推失败的；都成功过：全部再推一次
async function repush(r) {
  busy.value = r.id
  msg.value = ''
  try {
    const channels = r.status === 'sent' ? r.deliveries.map(d => d.channel) : null
    const res = await http.post(`/issues/${r.id}/repush`, { channels: channels && channels.length ? channels : null }, { timeout: 300000 })
    msgOk.value = res.status !== 'failed'
    msg.value = t('home.pushed.' + res.status, { n: r.total })
    await load()
  } catch (e) { msgOk.value = false; msg.value = e.message } finally { busy.value = 0 }
}
onMounted(load)
</script>

<style scoped>
.head { display: flex; align-items: baseline; gap: 16px; flex-wrap: wrap; border-bottom: 3px solid var(--rule-strong); margin-bottom: 8px; }
.head h1 { margin: 0 0 8px; font-size: 30px; }
.tbl-wrap { overflow-x: auto; }
.tbl { width: 100%; border-collapse: collapse; font-size: 14.5px; }
.tbl th { text-align: left; font-weight: 600; font-size: 13px; color: var(--muted); padding: 10px 10px 8px; border-bottom: 1px solid var(--rule-strong); white-space: nowrap; }
.tbl td { padding: 12px 10px; border-bottom: 1px solid var(--rule); vertical-align: top; }
.tbl .r { text-align: right; }
.kind { font-family: var(--serif); font-weight: 600; color: var(--ink); white-space: nowrap; }
.tag { margin-right: 10px; }
.err { margin-top: 4px; overflow-wrap: anywhere; }
</style>
