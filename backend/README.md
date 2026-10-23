# HonoCareer 后端

AI 面试 / 答辩陪练平台后端服务（FastAPI + SQLite + DeepSeek）。

## 目录结构

```
backend/
├── app/
│   ├── main.py                # FastAPI 启动入口，注册所有接口
│   ├── config.py              # 数据库、DeepSeek、JWT 等配置
│   ├── db/
│   │   ├── session.py         # SQLite 数据库连接和会话
│   │   └── models.py          # 所有数据库模型
│   ├── api/                   # 接口层，只处理请求和响应
│   ├── services/              # 普通业务逻辑
│   ├── agent/                 # AI Agent 核心逻辑
│   │   └── tools/             # Agent 可调用工具
│   ├── llm/                   # 大模型调用层
│   └── parsers/               # 文件解析模块
├── tests/                     # 自动化测试
├── docs/                      # 项目文档
├── requirements.txt
└── .env.example
```

## 环境要求

- Python 3.13+
- 依赖见 `requirements.txt`

## 启动方式

（待补充）

## 开发规范

（待补充）
