<script setup lang="ts">
import { useData, withBase } from "vitepress"
import { computed, ref } from "vue"
import manifest from "../../demos/manifest.json"
import scenarios from "../../demos/scenarios.json"

const props = defineProps<{ lesson: keyof typeof scenarios }>()
const { lang } = useData()
const zh = computed(() => lang.value.startsWith("zh"))
const content = computed(() => scenarios[props.lesson][zh.value ? "zh" : "en"])
const media = computed(() => (manifest as Record<string, { duration: number, recorded_on: string, files: Record<string, { sha256: string }> }>)[props.lesson])
const usesAi = computed(() => "ai_required" in scenarios[props.lesson] && scenarios[props.lesson].ai_required)
const failed = ref(false)
function asset(name: string) {
  const version = media.value?.files[name]?.sha256.slice(0, 12)
  return withBase(`/demos/${name}${version ? `?v=${version}` : ""}`)
}
</script>

<template>
  <article class="demo-lesson" :data-demo="lesson">
    <a :href="withBase(`/${zh ? 'zh' : 'en'}/learn/`)">{{ zh ? '← 入门与演示' : '← Getting started and demos' }}</a>
    <h1>{{ content.title }}</h1>
    <p class="demo-lead">
      {{ content.summary }}
    </p>
    <p class="demo-note">
      {{ zh ? '真实界面录制 · 虚构数据 · 中文 AI 配音 · 中英文字幕' : 'Real UI recording · Synthetic data · AI-generated Chinese narration · Chinese/English captions' }}
    </p>
    <template v-if="media">
      <video :key="`${lesson}-${lang}`" controls playsinline preload="metadata" :poster="asset(`${lesson}.png`)" :aria-label="content.title" @error="failed = true">
        <source :src="asset(`${lesson}.mp4`)" type="video/mp4">
        <track kind="captions" :src="asset(`${lesson}.zh.vtt`)" srclang="zh" label="简体中文" :default="zh">
        <track kind="captions" :src="asset(`${lesson}.en.vtt`)" srclang="en" label="English" :default="!zh">
        {{ zh ? '浏览器无法播放，请下载视频或阅读下方步骤。' : 'Download the video or follow the steps below if playback is unavailable.' }}
      </video>
      <p class="demo-note">
        {{ zh ? '点击播放收听中文讲解，可在播放器中静音或切换字幕。' : 'Press play for Chinese narration. Mute or switch captions in the player.' }}
        {{ usesAi ? (zh ? '本演示实际调用 AI 模型，需要实例开启 AI 并获得相应权限。' : 'This demonstration calls a real model and requires AI access on your instance.') : (zh ? '手工操作路径不需要开启 AI。' : 'The manual workflow does not require AI.') }}
      </p>
      <p v-if="failed" role="alert">
        {{ zh ? '视频暂时无法加载，可重试页面、下载视频或按下方指引操作。' : 'The video could not load. Retry, download it or use the written steps below.' }}
      </p>
      <div class="demo-downloads">
        <a :href="asset(`${lesson}.mp4`)" download>{{ zh ? '下载视频' : 'Download video' }}</a>
        <a :href="asset(`${lesson}.zh.vtt`)" download>{{ zh ? '中文字幕' : 'Chinese captions' }}</a>
        <a :href="asset(`${lesson}.en.vtt`)" download>{{ zh ? '英文字幕' : 'English captions' }}</a>
        <span>{{ media.recorded_on }} · {{ Math.round(media.duration) }} {{ zh ? '秒' : 'seconds' }}</span>
      </div>
      <p class="demo-note">
        {{ zh ? '录制于本地开发版；界面可能随版本变化，权限以当前实例为准。' : 'Recorded on a local development build with a Chinese UI; English captions are available. UI and permissions depend on your instance.' }}
      </p>
    </template>
    <p v-else>
      {{ zh ? '视频正在本地生成，可先阅读操作步骤。' : 'Video generation is in progress locally. Written steps are available below.' }}
    </p>
    <h2>{{ zh ? '开始前' : 'Before you start' }}</h2>
    <ul>
      <li v-for="text in content.requirements" :key="text">
        {{ text }}
      </li>
    </ul>
    <template v-if="scenarios[lesson].downloads.length">
      <h2>{{ zh ? '配套示例' : 'Example files' }}</h2>
      <p>{{ zh ? '只包含虚构数据。请在专用演示项目使用，勿混入正式科研数据。示例 CSV 仅匹配此示例 Protocol。' : 'Synthetic data only. Use a dedicated demo project, separate from research data. The example CSV matches this example Protocol only.' }}</p>
      <ul>
        <li v-for="name in scenarios[lesson].downloads" :key="name">
          <a :href="asset(`examples/${name}`)" download>{{ name }}</a>
        </li>
      </ul>
    </template>
    <h2>{{ zh ? '跟着做' : 'Follow along' }}</h2>
    <ol>
      <li v-for="text in content.steps" :key="text">
        {{ text }}
      </li>
    </ol>
    <div class="demo-success">
      <strong>{{ zh ? '完成后检查：' : 'Check the result: ' }}</strong>{{ content.success }}
    </div>
    <h2>{{ zh ? '遇到问题' : 'If you get stuck' }}</h2>
    <ul>
      <li v-if="usesAi">
        {{ zh ? '没有 Aira 入口或模型暂时不可用：检查实例 AI 配置及使用权限，也可从模板创建协议、手动填写和配置分析。模型输出可能不同，请核对后再保存。' : 'If Aira is unavailable, check instance configuration and access. Templates, manual forms and analysis configuration remain available. Model output may vary: review it before saving.' }}
      </li>
      <li>{{ zh ? '找不到创建或提交按钮：确认账号、所在项目和角色，必要时请项目管理员授权。' : 'Missing create or submit controls: check your account, project and role; ask the project administrator if needed.' }}</li>
      <li>{{ zh ? '没有“已保存”或成功提示：保留当前页面和输入，按错误提示处理，重新打开核对结果后再重试。' : 'No Saved or success confirmation: keep the page and inputs, follow the error message and check the destination before retrying.' }}</li>
      <li>{{ zh ? '看完仍不知道下一步：反馈卡住的步骤、页面及错误文字；请勿附带真实敏感数据或登录令牌。' : 'Still unclear: report the step, page and error text without sensitive research data or login tokens.' }}</li>
    </ul>
    <a :href="withBase(`/${zh ? 'zh' : 'en'}/learn/`)">{{ zh ? '选择下一个任务 →' : 'Choose your next task →' }}</a>
  </article>
</template>

<style scoped>
.demo-lesson video { display: block; width: 100%; max-height: 70vh; background: #171c2b; border: 1px solid #d8dfea; border-radius: 12px; }
.demo-lead { font-size: 1.1rem; }
.demo-note { color: var(--vp-c-text-2); font-size: .85rem; }
.demo-downloads { display: flex; flex-wrap: wrap; gap: 1rem; margin-top: .8rem; font-size: .9rem; }
.demo-success { padding: 16px; border-left: 3px solid var(--vp-c-brand-1); background: var(--vp-c-bg-soft); }
.demo-lesson li { margin-block: .75rem; }
.demo-lesson a { overflow-wrap: anywhere; }
</style>
