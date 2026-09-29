# 06 前端（packages/desktop）

Electron 桌面应用：`main/`（主进程）、`preload/`（桥接）、`renderer/`（React SPA，本档重点）。

## 技术栈

React 19 + TypeScript 5.5 + Vite 7 + Zustand 5 + TanStack Query 5 + React Router 7 + TailwindCSS 4（实际样式主体为**内联 style + CSS 变量**，Radix UI 仅声明未引用）。图标用 lucide-react。

## 入口与路由

`renderer/src/main.tsx`（BrowserRouter + QueryClientProvider）→ `App.tsx`：

| 路由 | 页面 | 功能 |
|------|------|------|
| /login | LoginPage | 登录（PublicOnlyRoute 守卫） |
| /dashboard | Dashboard | 项目列表 + 四步流水线导航 |
| /interpret | InterpretPage | 招标解读：上传→解析→AI 解读→评分矩阵→风险预警 |
| /generate | GeneratePage | 大纲编辑 + 逐章 AI 生成（SSE 流式渲染） |
| /check | CheckPage | 21 项检查 + 上传标书直接检查 |
| /format | FormatPage | 排版/格式检查/差异对比/美化，docx/doc/pdf 导出 |
| /news | NewsPage | 资讯热点/商机推荐/监控任务 |
| /settings | SettingsPage | 平台设置（见下） |

布局组件：`components/layout/`（AppLayout/Header/Sidebar，Sidebar 含角色可见性控制）；通用组件：`components/common/`（MarkdownRenderer：react-markdown+gfm+代码高亮+图片预览；StepHeader）。

## 状态管理与 API 封装

- **Zustand**：单 store `stores/appStore.ts`（persist 键 `bidmaster-app-store`，持久化 currentProjectId/token/user/sidebarCollapsed）
- **API 客户端**：`services/api.ts`（约 700 行单文件）
  - axios 实例：`baseURL: '/api'`、timeout 120s；请求拦截器注入 `localStorage.bidmaster_token` Bearer；响应拦截器 401 清 token 跳登录
  - `streamSSE()`：fetch 版 SSE 封装（生成页流式消费）
  - Vite dev 代理：端口 15168，`/api` → `http://localhost:18000`
- **API 分组**：authApi / projectApi / interpretApi / generateApi / checkApi / formatApi / mineruApi / skillApi / **llmApi** / newsApi / knowledgeApi / rbacApi / aiImageApi

## 设置页 `renderer/src/pages/SettingsPage.tsx`（约 2300 行单文件）

Tab 类型 `SettingsTab = 'agents' | 'llm' | 'rbac' | 'skills' | 'mineru'`：

| Tab | 渲染函数 | 内容 |
|-----|----------|------|
| 智能体模型 | `renderAgentsTab` | 7 个 Agent（interpret/outline/content/check/format/final_check/export）的模型/温度/max_tokens 配置；模型下拉选项由已启用 LLM 配置生成（value 格式 `provider_id/model`） |
| LLM 供应商 | `renderLLMTab` | 左卡：配置列表（Key 显隐/测试/设默认/编辑/删除）+ 新增/编辑对话框；右卡：供应商一览 + Token 用量。**支持 Sub2API 自定义网关**：选 sub2api 供应商后 API Base 必填，可点"获取模型列表"从网关动态拉取模型（调 `POST /llm/fetch-models`），`providerApiBases` 常量表存各供应商默认地址 |
| 权限管理 | `renderRbacTab` | 角色/权限树/用户管理 |
| Skill 管理 | `renderSkillsTab` | 只读列表 |
| MinerU OCR | `renderMineruTab` | cloud/self_hosted 模式、Key、endpoint、超时、轮询策略 |

### llmApi 方法一览（api.ts）

```
listProviders / testConnection / fetchModels / getUsage
getDefaultModel / setDefaultModel（写 .env 链路，UI 未直接使用）
listAgentModels / updateAgentModel / resetAgentModels
listConfigs / revealConfigKey / createConfig / updateConfig / deleteConfig / setDefaultConfig
```

### 前端类型

`LLMConfigItem`（id/provider_id/display_name/api_key_masked/has_api_key/api_base/default_model/is_default/enabled/note）、`AgentModel`、`MinerUConfig`。表单均为原生 input/select + 内联 style，无通用表单组件——新增设置 UI 时沿用 SettingsPage 对话框模式保持一致。

## 与桌面端的集成

主进程窗口/生命周期在 `main/`；`preload/` 暴露受限 IPC；生产模式加载 renderer 构建产物，dev 模式访问 Vite dev server。
