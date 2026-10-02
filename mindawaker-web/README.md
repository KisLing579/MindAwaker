# Mindawaker Web

Mindawaker 的现代化 React 前端，使用 Next.js 14 + TypeScript + Tailwind CSS + shadcn/ui 构建。

## ✨ 特性

- 🎨 现代化 UI 设计，渐变色彩和流畅动画
- 🧙‍♂️ 向导式视频生成配置
- 📊 实时 WebSocket 进度显示
- 🛑 随时可撤回生成任务
- 📱 响应式布局，支持移动端
- 🔄 项目历史管理

## 🚀 快速开始

### 1. 安装依赖

```bash
cd mindawaker-web
npm install
```

### 2. 配置代理

`next.config.js` 已配置代理到后端服务 (端口 8000)。
如需修改后端地址，请编辑：

```javascript
async rewrites() {
  return [
    {
      source: '/api/:path*',
      destination: 'http://127.0.0.1:8000/:path*',
    },
  ];
}
```

### 3. 启动开发服务器

```bash
npm run dev
```

访问 http://localhost:3000

### 4. 构建生产版本

```bash
npm run build
npm start
```

## 📁 项目结构

```
mindawaker-web/
├── src/
│   ├── app/                 # Next.js App Router
│   │   ├── layout.tsx       # 根布局
│   │   ├── page.tsx         # 主页面
│   │   └── globals.css      # 全局样式
│   ├── components/          # React 组件
│   │   ├── ui/              # shadcn/ui 组件
│   │   │   ├── button.tsx
│   │   │   ├── card.tsx
│   │   │   ├── progress.tsx
│   │   │   └── ...
│   │   └── VideoGenerator/  # 视频生成组件
│   │       └── index.tsx
│   ├── hooks/               # 自定义 Hooks
│   │   └── useTask.ts       # 任务管理 Hook
│   └── lib/                 # 工具函数
│       └── utils.ts
├── public/                  # 静态资源
├── next.config.js           # Next.js 配置
├── tailwind.config.ts       # Tailwind 配置
└── package.json
```

## 🔌 API 接口

前端通过以下接口与后端通信：

| 接口 | 方法 | 描述 |
|------|------|------|
| `/api/video/compose` | POST | 创建视频任务 |
| `/api/video/cancel/:id` | POST | 取消任务 |
| `/api/video/task/:id` | GET | 查询任务状态 |
| `/ws://:id` | WebSocket | 实时进度推送 |

## 🎨 UI 组件

使用 shadcn/ui 组件库：

- **Button** - 按钮（支持渐变样式）
- **Card** - 卡片容器
- **Progress** - 进度条（支持渐变）
- **Input** - 输入框
- **Select** - 下拉选择
- **Tabs** - 标签页
- **Badge** - 徽章标签

## 📝 开发说明

### 添加新页面

在 `src/app/` 目录下创建新文件夹：

```bash
mkdir src/app/new-page
touch src/app/new-page/page.tsx
```

### 添加新组件

```bash
# 创建组件文件
touch src/components/MyComponent/index.tsx

# 导出组件
echo "export { default } from './MyComponent';" > src/components/MyComponent/index.ts
```

### 样式指南

- 使用 Tailwind CSS 工具类
- 颜色变量来自 `globals.css` 的 CSS 变量
- 圆角使用 `rounded-md` (6px) 或 `rounded-lg` (8px)
- 阴影使用 `shadow-sm`, `shadow`, `shadow-lg`

## 🔗 相关项目

- [Mindawaker Backend](../) - Python FastAPI 后端
