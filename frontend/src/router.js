import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/setup', name: 'setup', component: () => import('./views/Setup.vue'), meta: { bare: true, open: true } },
  { path: '/login', name: 'login', component: () => import('./views/Login.vue'), meta: { bare: true, open: true } },
  // 推送消息里「查看全部」打开的只读页：凭链接里的令牌访问，不用登录
  { path: '/i/:id', name: 'public', component: () => import('./views/Public.vue'), meta: { bare: true, open: true, public: true } },
  { path: '/', name: 'home', component: () => import('./views/Home.vue') },
  { path: '/issues/:id', name: 'issue', component: () => import('./views/Home.vue') },
  { path: '/history', name: 'history', component: () => import('./views/History.vue') },
  { path: '/settings/:tab?', name: 'settings', component: () => import('./views/Settings.vue') },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({ history: createWebHistory(), routes, scrollBehavior: () => ({ top: 0 }) })

router.beforeEach(async to => {
  if (to.meta.public) return true
  const { auth, checkSetup, setupState } = await import('./api.js')
  if (!setupState.checked || !setupState.configured) {
    try { await checkSetup() } catch (e) { /* 后端暂时连不上：照常走，接口报错时再提示 */ }
  }
  if (!setupState.configured && to.name !== 'setup') return { name: 'setup' }
  if (to.meta.open) return true
  if (!auth.token) return { name: 'login', query: { next: to.fullPath } }
  return true
})

export default router
