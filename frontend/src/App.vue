<template>
  <router-view v-if="route.meta.bare" />
  <div v-else class="shell">
    <header class="top">
      <div class="wrap bar">
        <router-link to="/" class="logo" :aria-label="t('app.name')">{{ t('app.name') }}</router-link>
        <nav class="nav" :aria-label="t('nav.label')">
          <router-link to="/" :class="{ on: route.name === 'home' || route.name === 'issue' }"><Newspaper :size="18" aria-hidden="true" /><span>{{ t('nav.home') }}</span></router-link>
          <router-link to="/history" :class="{ on: route.name === 'history' }"><History :size="18" aria-hidden="true" /><span>{{ t('nav.history') }}</span></router-link>
          <router-link to="/settings" :class="{ on: route.name === 'settings' }"><Settings :size="18" aria-hidden="true" /><span>{{ t('nav.settings') }}</span></router-link>
        </nav>
        <span class="sp" />
        <button class="btn ghost sm icon" @click="toggleLang" :aria-label="t('nav.lang')" :title="t('nav.lang')"><Languages :size="18" aria-hidden="true" /></button>
        <button class="btn ghost sm icon" @click="toggleTheme" :aria-label="t('nav.theme')" :title="t('nav.theme')">
          <Moon v-if="!dark" :size="18" aria-hidden="true" /><Sun v-else :size="18" aria-hidden="true" /></button>
        <button class="btn ghost sm icon" @click="logout" :aria-label="t('nav.logout')" :title="t('nav.logout')"><LogOut :size="18" aria-hidden="true" /></button>
      </div>
    </header>
    <main class="wrap main"><router-view /></main>
    <footer class="wrap foot">{{ t('app.name') }} v{{ version }} · {{ t('app.by') }}</footer>
  </div>
</template>

<script setup>
import { History, Languages, LogOut, Moon, Newspaper, Settings, Sun } from '@lucide/vue'
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import http, { setAuth } from './api.js'
import { setLang } from './i18n/index.js'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const version = ref('')
const media = window.matchMedia('(prefers-color-scheme: dark)')
const dark = ref(document.documentElement.dataset.theme ? document.documentElement.dataset.theme === 'dark' : media.matches)

function toggleTheme() {
  dark.value = !dark.value
  const v = dark.value ? 'dark' : 'light'
  document.documentElement.dataset.theme = v
  try { localStorage.setItem('mynews.theme', v) } catch (e) { /* ignore */ }
}
function toggleLang() { setLang(locale.value === 'zh' ? 'en' : 'zh') }
function logout() { setAuth(''); router.push({ name: 'login' }) }
onMounted(async () => { try { version.value = (await http.get('/health')).version } catch (e) { /* ignore */ } })
</script>

<style scoped>
.top { border-bottom: 1px solid var(--rule); background: var(--paper); position: sticky; top: 0; z-index: 10; }
.bar { display: flex; align-items: center; gap: 4px; min-height: 56px; }
.logo { font: 700 20px/1 var(--serif); color: var(--brand); margin-right: 20px; white-space: nowrap; }
.logo:hover { text-decoration: none; }
.nav { display: flex; gap: 2px; }
.nav a { display: inline-flex; align-items: center; gap: 6px; min-height: 44px; padding: 0 12px; color: var(--muted); font-size: 15px;
  border-bottom: 2px solid transparent; }
.nav a:hover { color: var(--ink); text-decoration: none; }
.nav a.on { color: var(--ink); border-bottom-color: var(--brand); font-weight: 600; }
.sp { flex: 1; }
.icon { width: 40px; padding: 0; }
.main { padding-top: 24px; padding-bottom: 48px; }
.foot { padding-top: 16px; padding-bottom: 32px; border-top: 1px solid var(--rule); font-size: 13px; color: var(--muted); }
@media (max-width: 640px) {
  .logo { margin-right: 8px; font-size: 18px; }
  .nav a span { display: none; }
  .nav a { padding: 0 10px; }
}
</style>
