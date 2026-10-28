<template>
  <!-- 一期的版面：报头 + 今日要点 + 分类分栏。首页和「查看全部」只读页共用 -->
  <article class="issue">
    <header class="mast">
      <div class="mast-top">
        <span class="date">{{ longDate(issue.window_end) }}</span>
        <span class="sp" />
        <slot name="tools" />
      </div>
      <h1 class="name">{{ t('app.name') }}</h1>
      <div class="mast-sub">
        <span class="kind">{{ t('kind.' + issue.kind) }}</span>
        <span class="num">{{ t('issue.count', { n: issue.total, c: issue.sections.length }) }}</span>
        <span class="num muted">{{ span(issue.window_start, issue.window_end) }}</span>
        <slot name="status" />
      </div>
    </header>

    <div v-if="!issue.total" class="empty">{{ t('issue.none') }}</div>

    <section v-if="issue.ai_points && issue.ai_points.length" class="points" :aria-label="t('issue.points')">
      <h2>{{ t('issue.points') }}</h2>
      <ol>
        <li v-for="(p, i) in issue.ai_points" :key="i">
          <span>{{ p.text }}</span>
          <template v-for="(r, j) in p.refs" :key="j">
            <a v-if="r.url" class="ref" :href="r.url" target="_blank" rel="noopener noreferrer" :title="r.title">{{ t('issue.source') }}</a>
          </template>
        </li>
      </ol>
    </section>
    <p v-else-if="issue.ai_error" class="ai-err" role="note"><AlertTriangle :size="16" aria-hidden="true" />{{ t('issue.aiFailed', { e: issue.ai_error }) }}</p>

    <div class="cols">
      <section v-for="s in issue.sections" :key="s.category" class="sec">
        <h2><span>{{ s.category }}</span><span class="cnt num">{{ s.items.length }}</span></h2>
        <ul>
          <li v-for="it in s.items" :key="it.id">
            <a v-if="it.url" class="ttl" :href="it.url" target="_blank" rel="noopener noreferrer">{{ it.title }}</a>
            <span v-else class="ttl">{{ it.title }}</span>
            <div class="meta"><span v-if="it.source">{{ it.source }}</span><span class="num">{{ hm(it.crawled) }}</span></div>
            <p v-if="it.summary" class="sum">{{ it.summary }}</p>
          </li>
        </ul>
      </section>
    </div>
  </article>
</template>

<script setup>
import { AlertTriangle } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { hm, longDate, span } from '../format.js'

defineProps({ issue: { type: Object, required: true } })
const { t } = useI18n()
</script>

<style scoped>
/* 报头：粗细双线夹着刊名 */
.mast { border-top: 3px solid var(--rule-strong); border-bottom: 1px solid var(--rule-strong); padding: 10px 0 14px; position: relative; }
.mast::before { content: ""; position: absolute; left: 0; right: 0; top: 4px; border-top: 1px solid var(--rule-strong); }
.mast-top { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding-top: 8px; font-size: 14px; color: var(--muted); min-height: 40px; }
.mast-top .sp { flex: 1; }
.name { margin: 4px 0 6px; font: 700 56px/1.05 var(--serif); letter-spacing: -0.5px; color: var(--brand); text-align: center; }
.mast-sub { display: flex; justify-content: center; align-items: center; gap: 8px 18px; flex-wrap: wrap; font-size: 14px; }
.kind { font-family: var(--serif); font-weight: 700; font-size: 16px; }

.points { margin: 28px 0 8px; padding: 18px 0 6px; border-bottom: 1px solid var(--rule); }
.points h2, .sec h2 { margin: 0 0 12px; font-size: 22px; line-height: 1.3; }
.points ol { margin: 0; padding-left: 1.6em; display: grid; gap: 8px; }
.points li { line-height: 1.7; }
.ref { margin-left: 6px; font-size: 13px; white-space: nowrap; }
.ai-err { display: flex; gap: 8px; align-items: flex-start; margin: 20px 0 0; padding: 10px 12px; border-left: 3px solid var(--warn);
  background: var(--wash); color: var(--ink); font-size: 14px; line-height: 1.6; }
.ai-err svg { color: var(--warn); flex: none; margin-top: 3px; }

/* 分类分栏：宽屏两栏 */
.cols { columns: 2; column-gap: 48px; margin-top: 24px; }
.sec { break-inside: avoid-column; margin-bottom: 28px; }
.sec h2 { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; padding-bottom: 6px; border-bottom: 1px solid var(--rule-strong); }
.cnt { font: 500 13px var(--sans); color: var(--muted); }
.sec ul { list-style: none; margin: 0; padding: 0; }
.sec li { padding: 12px 0; border-bottom: 1px solid var(--rule); }
.sec li:last-child { border-bottom: 0; }
.ttl { display: block; color: var(--ink); font-weight: 600; font-size: 16px; line-height: 1.5; }
a.ttl:hover { color: var(--link); }
.meta { display: flex; gap: 10px; margin-top: 2px; font-size: 13px; color: var(--muted); }
.sum { margin: 4px 0 0; font-size: 14.5px; line-height: 1.65; color: var(--muted); }
@media (max-width: 960px) { .cols { columns: 1; } }
@media (max-width: 640px) { .name { font-size: 36px; } .mast-sub { justify-content: flex-start; } .name { text-align: left; } }
</style>
