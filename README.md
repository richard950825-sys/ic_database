# IC/BCD 智能知识库系统

基于 FastAPI、LangGraph 和 Google Gemini 1.5/2.0 构建的 IC 设计与 BCD 工艺领域高精度多模态知识库系统。

## 🌟 核心功能

### 1. 混合解析策略 (Hybrid Parsing Strategy)
-   **原生 PDF 加速**: 使用 `docling` 直接解析 PDF 结构提取文本和表格（速度：毫秒级）。
-   **视觉理解兜底**: 自动检测扫描版表格或复杂图片，路由至 **多模态大模型 (Gemini)** 进行语义重构（精度：高）。
-   **灵活配置**: 可在 `core/config.py` 中切换 `USE_OCR` 开关，在“极速模式（混合）”和“全面 OCR 模式”间切换。

### 2. 图谱增强检索 (Process GraphRAG)
-   **知识图谱**: 利用 Neo4j 自动提取并构建实体（如“器件”、“参数”）及其关联关系。
-   **向量检索**: 使用本地 `BAAI/bge-m3` 或 Gemini 对文本块构建语义索引，存储于 Qdrant。
-   **智能路由**: 根据用户意图自动选择最佳检索策略（精确匹配、图谱遍历或语义搜索）。

### 3. 审计式生成 (Audited Generation)
-   **分级质检**: 关键数据（红色分级）经过多轮 AI 交叉验证。
-   **溯源引用**: 所有回答均严格标注来源文件页码及具体内容块。

## 🛠️ 技术栈

-   **后端**: Python 3.12, FastAPI, Uvicorn
-   **编排**: LangGraph, LangChain
-   **AI 模型**: Google Gemini (via `google-genai` SDK)
-   **数据库**:
    -   Neo4j (图数据库)
    -   Qdrant (向量数据库)
-   **前端**: 原生 HTML/JS/CSS (无复杂框架依赖), Markdown 渲染

## 🚀 快速开始

### 1. 前置要求
-   Python 3.10+
-   Docker (用于运行数据库)
-   Google Gemini API Key

### 2. 环境配置

```bash
# 创建虚拟环境
python -m venv venv
.\venv\Scripts\activate  # Windows
# source venv/bin/activate # Linux/Mac

# 安装依赖
pip install -r requirements.txt
```

### 3. 系统配置
复制 `.env.example` 为 `.env` 并填入密钥：

```ini
GOOGLE_API_KEY=your_key_here
NEO4J_URI=bolt://localhost:7687
NEO4J_PASSWORD=password
QDRANT_URL=http://localhost:6333
# 如需代理请配置
# HTTPS_PROXY=http://127.0.0.1:7890
```

### 4. 启动数据库
```bash
# Qdrant 向量库
docker run -d -p 6333:6333 qdrant/qdrant

# Neo4j 图数据库
docker run -d -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/password neo4j
```

### 5. 启动服务
```bash
python server.py
# 服务将运行在 http://localhost:8000
```

## 📂 项目结构

-   `server.py`: FastAPI 主程序及 API 接口。
-   `core/`: 核心逻辑 (解析器, 向量库, 图数据库, 配置)。
-   `agents/`: LangGraph 节点 (路由, 检索, 分析)。
-   `static/`: 前端静态资源 (HTML, CSS, JS)。
-   `utils/`: 工具类 (Gemini 客户端, 日志)。

## 💡 使用指南

1.  **上传文档**: 拖拽 PDF 文件至上传区。系统会自动进行混合解析，提取实体并构建索引。
2.  **专业问答**: 提出技术问题（例如：“LDMOS 器件的击穿电压是多少？”）。
3.  **图谱溯源**: 系统给出的每个论断都会链接到具体的文档和页码。

## 许可证
MIT