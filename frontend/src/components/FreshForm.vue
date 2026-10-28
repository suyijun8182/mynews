<template>
  <!-- FreshRSS 连接：设置页和安装向导共用。API 密码在 FreshRSS 设置 → 账户 → API 管理里设，不是登录密码 -->
  <form class="form" @submit.prevent="save">
    <div class="field">
      <label for="fr-url">{{ t('fresh.url') }}</label>
      <input id="fr-url" class="input addr" v-model.trim="f.url" placeholder="https://rss.example.com" autocomplete="off" required />
      <small>{{ t('fresh.urlHint') }}</small>
    </div>
    <div class="two">
      <div class="field">
        <label for="fr-user">{{ t('fresh.user') }}</label>
        <input id="fr-user" class="input" v-model.trim="f.username" autocomplete="off" required />
      </div>
      <div class="field">
        <label for="fr-pw">{{ t('fresh.pw') }}</label>
        <input id="fr-pw" class="input" type="password" v-model="f.api_password" autocomplete="new-password" required />
      </div>
    </div>
    <details class="how">
      <summary>{{ t('fresh.howTitle') }}</summary>
      <ol><li v-for="i in 3" :key="i">{{ t('fresh.how' + i) }}</li></ol>
    </details>
    <p v-if="okMsg" class="okc small" role="status">{{ okMsg }}</p>
    <p v-if="err" class="err" role="alert">{{ err }}</p>
    <div class="acts">
      <button type="button" class="btn" :disabled="!!busy || !valid" @click="test">{{ busy === 'test' ? t('common.testing') : t('fresh.test') }}</button>
      <button class="btn primary" :disabled="!!busy || !valid">{{ busy === 'save' ? t('common.saving') : saveText || t('common.save') }}</button>
    </div>
  </form>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import http from '../api.js'

defineProps({ saveText: String })
const emit = defineEmits(['saved'])
const { t } = useI18n()
const f = reactive({ url: '', username: '', api_password: '', categories: [] })
const busy = ref('')
const err = ref('')
const okMsg = ref('')
const valid = computed(() => f.url && f.username && f.api_password)

onMounted(async () => { try { Object.assign(f, await http.get('/settings/freshrss')) } catch (e) { err.value = e.message } })

async function test() {
  err.value = okMsg.value = ''
  busy.value = 'test'
  try {
    const r = await http.post('/settings/freshrss/test', f, { timeout: 60000 })
    okMsg.value = t('fresh.ok', { n: r.categories.length })
  } catch (e) { err.value = e.message } finally { busy.value = '' }
}

async function save() {
  err.value = okMsg.value = ''
  busy.value = 'save'
  try {
    await http.post('/settings/freshrss/test', f, { timeout: 60000 })   // 先确认连得上再存
    Object.assign(f, await http.put('/settings/freshrss', f))
    okMsg.value = t('common.saved')
    emit('saved')
  } catch (e) { err.value = e.message } finally { busy.value = '' }
}
</script>

<style scoped>
.form { display: flex; flex-direction: column; gap: 16px; }
.two { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.how { font-size: 14px; color: var(--muted); }
.how summary { cursor: pointer; color: var(--link); min-height: 32px; display: flex; align-items: center; }
.how ol { margin: 4px 0 0; padding-left: 20px; line-height: 1.8; }
.acts { display: flex; gap: 10px; justify-content: flex-end; flex-wrap: wrap; }
p { margin: 0; }
@media (max-width: 640px) { .two { grid-template-columns: minmax(0, 1fr); } }
</style>
