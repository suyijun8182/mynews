<template>
  <!-- 推送消息里「查看全部」打开的只读页：不用登录，凭链接里的令牌 -->
  <div class="wrap page">
    <IssueView v-if="issue" :issue="issue" />
    <div v-else-if="err" class="gone">
      <h1>{{ t('app.name') }}</h1>
      <p class="muted">{{ err }}</p>
    </div>
    <div v-else class="empty">{{ t('common.loading') }}</div>
    <footer class="foot">{{ t('app.name') }} · {{ t('public.note') }}</footer>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import http from '../api.js'
import IssueView from '../components/IssueView.vue'

const { t } = useI18n()
const route = useRoute()
const issue = ref(null)
const err = ref('')

onMounted(async () => {
  try { issue.value = await http.get(`/public/issues/${encodeURIComponent(route.params.id)}`, { params: { t: route.query.t || '' } }) }
  catch (e) { err.value = e.response?.status === 404 || e.response?.status === 422 ? t('public.gone') : e.message }
})
</script>

<style scoped>
.page { padding-top: 24px; padding-bottom: 32px; }
.gone { text-align: center; margin: 80px auto; }
.gone h1 { color: var(--brand); font-size: 40px; margin: 0 0 8px; }
.foot { margin-top: 24px; padding-top: 16px; border-top: 1px solid var(--rule); font-size: 13px; color: var(--muted); }
</style>
