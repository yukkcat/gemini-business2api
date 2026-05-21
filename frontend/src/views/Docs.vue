<template>
  <div class="space-y-6">
    <section class="ui-panel">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p class="ui-section-title">帮助中心</p>
          <p class="mt-1 text-xs text-muted-foreground">
            快速上手、接口示例、油猴导入助手与使用说明。
          </p>
        </div>
      </div>

      <div class="ui-segmented mt-6 text-xs">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          class="ui-segmented-btn flex-1 justify-center px-4 py-2"
          :class="activeTab === tab.id ? 'ui-segmented-btn-active' : ''"
          @click="activeTab = tab.id"
        >
          {{ tab.label }}
        </button>
      </div>

      <div class="mt-6 space-y-6 text-sm text-foreground">
        <div v-if="activeTab === 'api'" class="space-y-6">
          <div class="space-y-2">
            <p class="text-sm font-semibold">账号配置格式</p>
            <p class="mt-1 text-xs text-muted-foreground">
              支持 <code>accounts.json</code>、环境变量 <code>ACCOUNTS_CONFIG</code>，以及后台导入 JSON。
            </p>
            <pre class="mt-3 overflow-x-auto whitespace-pre-wrap rounded-2xl border border-border bg-card px-4 py-3 text-xs font-mono scrollbar-slim">[
  {
    "id": "account_1",
    "secure_c_ses": "CSE.Ad...",
    "csesidx": "498...",
    "config_id": "0cd...",
    "host_c_oses": "",
    "expires_at": "2026-12-31 23:59:59"
  }
]</pre>
            <p class="mt-2 text-xs text-muted-foreground">
              必填：<code>secure_c_ses</code> / <code>csesidx</code> / <code>config_id</code>；
              <code>id</code>、<code>host_c_oses</code>、<code>expires_at</code> 可选。
            </p>
          </div>

          <div class="space-y-2">
            <p class="text-sm font-semibold">API 对话 curl 示例</p>
            <p class="mt-1 text-xs text-muted-foreground">
              标准 OpenAI 兼容格式，支持流式与非流式输出。
            </p>
            <pre class="mt-3 overflow-x-auto whitespace-pre-wrap rounded-2xl border border-border bg-card px-4 py-3 text-xs font-mono scrollbar-slim">curl -X POST "http://localhost:7860/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{
    "model": "gemini-3.1-flash",
    "stream": false,
    "temperature": 0.7,
    "messages": [
      { "role": "system", "content": "你是一个简洁的助手" },
      { "role": "user", "content": "介绍一下这个项目" }
    ]
  }'</pre>
            <p class="mt-2 text-xs text-muted-foreground">
              如果未设置 API Key，可省略 <code>Authorization</code>。
            </p>
          </div>

          <div class="space-y-2">
            <p class="text-sm font-semibold">图片生成示例</p>
            <p class="mt-1 text-xs text-muted-foreground">
              图片生成与编辑支持 URL / Base64 输入，默认输出格式由系统设置控制。
            </p>
            <div class="mt-3 grid gap-3 md:grid-cols-2">
              <pre class="overflow-x-auto whitespace-pre-wrap rounded-2xl border border-border bg-card px-4 py-3 text-xs font-mono scrollbar-slim">curl -X POST "http://localhost:7860/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{
    "model": "gemini-imagen",
    "stream": false,
    "messages": [
      { "role": "user", "content": "生成一只赛博风格的猫" }
    ]
  }'</pre>
              <pre class="overflow-x-auto whitespace-pre-wrap rounded-2xl border border-border bg-card px-4 py-3 text-xs font-mono scrollbar-slim">curl -X POST "http://localhost:7860/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{
    "model": "gemini-3.1-flash",
    "stream": false,
    "messages": [
      {
        "role": "user",
        "content": [
          { "type": "text", "text": "把图片改成插画风格" },
          { "type": "image_url", "image_url": { "url": "https://example.com/cat.png" } }
        ]
      }
    ]
  }'</pre>
            </div>
          </div>

          <div class="space-y-2">
            <p class="text-sm font-semibold">视频生成示例</p>
            <p class="mt-1 text-xs text-muted-foreground">
              使用 <code>gemini-veo</code> 走统一的对话接口，输出格式由系统设置统一控制。
            </p>
            <pre class="mt-3 overflow-x-auto whitespace-pre-wrap rounded-2xl border border-border bg-card px-4 py-3 text-xs font-mono scrollbar-slim">curl -X POST "http://localhost:7860/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{
    "model": "gemini-veo",
    "stream": true,
    "messages": [
      { "role": "user", "content": "生成一段可爱猫咪玩耍的视频" }
    ]
  }'</pre>
          </div>

          <div class="space-y-2">
            <p class="text-sm font-semibold">常用接口</p>
            <div class="overflow-x-auto rounded-2xl border border-border bg-card">
              <table class="min-w-full text-left text-xs">
                <thead class="bg-muted/40 text-muted-foreground">
                  <tr>
                    <th class="px-4 py-3 font-medium">Endpoint</th>
                    <th class="px-4 py-3 font-medium">Method</th>
                    <th class="px-4 py-3 font-medium">说明</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="endpoint in endpoints" :key="endpoint.path" class="border-t border-border">
                    <td class="px-4 py-3 font-mono text-[11px]">{{ endpoint.path }}</td>
                    <td class="px-4 py-3">{{ endpoint.method }}</td>
                    <td class="px-4 py-3 text-muted-foreground">{{ endpoint.description }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <div v-else-if="activeTab === 'helper'" class="space-y-6">
          <div class="space-y-2">
            <p class="text-sm font-semibold">油猴导入助手</p>
            <p class="mt-1 text-xs text-muted-foreground">
              用于从 Gemini Business 页面一键复制可导入账号 JSON。
            </p>
            <div class="grid gap-3 md:grid-cols-2">
              <div class="rounded-2xl border border-border bg-card p-4">
                <p class="font-medium text-foreground">安装位置</p>
                <ul class="mt-3 space-y-2 text-xs text-muted-foreground">
                  <li>
                    安装地址：
                    <a :href="tampermonkeyUrl" target="_blank" rel="noreferrer" class="text-primary hover:underline">
                      gemini-business-import.user.js
                    </a>
                  </li>
                  <li>仓库路径：<code>tools/tampermonkey/gemini-business-import.user.js</code></li>
                  <li>点击 <code>Copy JSON</code> 复制；<code>Shift + Click</code> 下载 JSON</li>
                  <li>导出的 <code>expires_at</code> 默认是当前时间 + 12 小时</li>
                </ul>
              </div>

              <div class="rounded-2xl border border-amber-200 bg-amber-50 p-4">
                <p class="font-medium text-amber-700">使用前必须检查</p>
                <ol class="mt-3 space-y-2 text-xs leading-relaxed text-amber-800">
                  <li>1. Tampermonkey → 通用 → 配置模式：<code>高级</code></li>
                  <li>2. Tampermonkey → 安全 → 允许脚本访问 Cookie：<code>All</code></li>
                  <li>3. 如果仍然没有权限，请在浏览器扩展页开启<strong>开发者模式</strong></li>
                  <li>4. 修改后刷新 <code>business.gemini.google</code> 页面再试</li>
                </ol>
              </div>
            </div>
          </div>

          <div class="space-y-2">
            <p class="text-sm font-semibold">导入流程</p>
            <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              <div v-for="step in helperSteps" :key="step.title" class="rounded-2xl border border-border bg-card p-4">
                <p class="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">{{ step.index }}</p>
                <p class="mt-2 text-sm font-medium text-foreground">{{ step.title }}</p>
                <p class="mt-2 text-xs leading-relaxed text-muted-foreground">{{ step.description }}</p>
              </div>
            </div>
          </div>

          <div class="space-y-2">
            <p class="text-sm font-semibold">复制出的 JSON 示例</p>
            <pre class="mt-3 overflow-x-auto whitespace-pre-wrap rounded-2xl border border-border bg-card px-4 py-3 text-xs font-mono scrollbar-slim">[
  {
    "id": "you@example.com",
    "secure_c_ses": "CSE.Ad...",
    "csesidx": "498...",
    "config_id": "0cd...",
    "host_c_oses": "",
    "expires_at": "2026-04-25 12:00:00"
  }
]</pre>
            <p class="mt-2 text-xs text-muted-foreground">
              后台账号管理支持直接粘贴这类 JSON，也支持逐行文本导入。
            </p>
          </div>
        </div>

        <div v-else class="space-y-6">
          <div class="rounded-2xl border border-rose-200 bg-rose-50 p-4">
            <p class="font-medium text-rose-700">非商业用途提醒</p>
            <p class="mt-2 text-xs leading-relaxed text-rose-700">
              本项目采用 CNC-1.0 协议，当前主线定位为 2API 主服务与管理后台，不包含注册机等旧链路。
            </p>
          </div>

          <div class="grid gap-3 md:grid-cols-2">
            <div class="rounded-2xl border border-border bg-card p-4">
              <p class="font-medium text-foreground">适用场景</p>
              <ul class="mt-3 space-y-2 text-xs leading-relaxed text-muted-foreground">
                <li>• 个人学习与技术研究</li>
                <li>• 浏览器自动化与接口兼容性测试</li>
                <li>• 非商业技术交流</li>
              </ul>
            </div>

            <div class="rounded-2xl border border-border bg-card p-4">
              <p class="font-medium text-foreground">请同时遵守</p>
              <ul class="mt-3 space-y-2 text-xs leading-relaxed text-muted-foreground">
                <li>• Google 服务条款</li>
                <li>• Google Workspace 附加条款</li>
                <li>• Microsoft 服务协议</li>
                <li>• 相关邮箱服务商条款</li>
              </ul>
            </div>
          </div>

          <div class="rounded-2xl border border-border bg-card p-4">
            <p class="font-medium text-foreground">联系我们</p>
            <p class="mt-2 text-xs text-muted-foreground">
              Business2API 交流群：
              <a :href="communityUrl" target="_blank" rel="noreferrer" class="text-primary hover:underline">
                {{ communityUrl }}
              </a>
            </p>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

type TabId = 'api' | 'helper' | 'disclaimer'

const activeTab = ref<TabId>('api')
const tampermonkeyUrl = 'https://raw.githubusercontent.com/yukkcat/gemini-business2api/main/tools/tampermonkey/gemini-business-import.user.js'
const communityUrl = 'https://qm.qq.com/q/yegwCqJisS'

const tabs: Array<{ id: TabId; label: string }> = [
  { id: 'api', label: 'API 文档' },
  { id: 'helper', label: '导入助手' },
  { id: 'disclaimer', label: '使用说明' },
]

const endpoints = [
  { path: '/v1/models', method: 'GET', description: '模型列表' },
  { path: '/v1/chat/completions', method: 'POST', description: '对话补全 / 图片 / 视频统一入口' },
  { path: '/v1/images/generations', method: 'POST', description: '图片生成' },
  { path: '/v1/images/edits', method: 'POST', description: '图片编辑' },
  { path: '/health', method: 'GET', description: '健康检查' },
]

const helperSteps = [
  {
    index: 'STEP 1',
    title: '安装脚本',
    description: '先安装 Tampermonkey，再打开脚本地址完成安装。',
  },
  {
    index: 'STEP 2',
    title: '打开权限',
    description: '把配置模式改为高级，并允许脚本访问 Cookie。',
  },
  {
    index: 'STEP 3',
    title: '进入页面',
    description: '打开 business.gemini.google 的有效业务页面，确保页面里能读到 csesidx / config_id。',
  },
  {
    index: 'STEP 4',
    title: '导入后台',
    description: '复制或下载 JSON 后，到账号管理页面直接粘贴导入。',
  },
]
</script>
