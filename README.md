# IC/BCD 智能知识库系统

基于 FastAPI、LangGraph 和 Google Gemini 1.5/2.0 构建的 IC 设计与 BCD 工艺领域高精度多模态知识库系统。

## 🌟 核心功能

### 1. 混合解析策略 (Hybrid Parsing Strategy)
-   **智能分块**: 使用 `Smart Chunking` 和 `Chunk Merger` 算法，自动将破碎的文本行合并为语义段落，并识别潜在表格区域。
-   **混合分级**: 结合关键词规则 (Level 1) 和各类原型向量语义相似度 (Level 2) 进行内容分级。
    -   **RED**: 关键工艺参数，使用 **Gemini 2.0 Pro** 精准提取。
    -   **YELLOW**: 表格与技术指标，使用 **Adaptive Entity Extraction** 提取结构化数据。
    -   **GREEN**: 通用文本，快速入库。
-   **灵活配置**: 可在 `core/config.py` 中切换 `USE_OCR` 开关。

### 2. 自适应实体提取 (Adaptive Entity Extraction)
-   **Tier-Specific Prompts**: 针对不同分级内容加载专用 Prompt（如 RED 层的工艺参数模板、YELLOW 层的关系映射模板）。
-   **图谱增强**: 利用 Neo4j 构建高精度知识图谱，支持跨段落实体关联。
-   **向量检索**: 使用本地 `BAAI/bge-m3` 构建语义索引，存储于 Qdrant。

### 3. 性能与体验优化
-   **批处理 (Batching)**: 支持多块并发验证，减少 API 调用延迟。
-   **自动浏览器**: 启动服务时自动打开默认浏览器访问 Web 界面。
-   **任务管理**: 支持任务取消即时清理数据库，界面侧边栏自动维护任务状态。

## 🛠️ 技术栈

-   **后端**: Python 3.12, FastAPI, Uvicorn (Web Server)
-   **编排**: LangGraph, LangChain
-   **AI 模型**: Google Gemini (via `google-genai` SDK)
-   **数据库**:
    -   Neo4j (图数据库: 实体关系)
    -   Qdrant (向量数据库: 语义检索)
-   **前端**: 原生 HTML/JS/CSS (极简设计，Unified UI Style)

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

# 安装依赖 (已新增 pypdf, numpy)
pip install -r requirements.txt
```

### 3. 系统配置
复制 `.env.example` 为 `.env` 并填入密钥：

```ini
GOOGLE_API_KEY=your_key_here
NEO4J_URI=bolt://localhost:17687
NEO4J_PASSWORD=password
QDRANT_URL=http://localhost:6333
# 如需代理请配置
# HTTPS_PROXY=http://127.0.0.1:7890
```

### 4. 启动数据库
使用提供的脚本自动启动服务（已处理端口冲突，使用 17474/17687 端口）：
```powershell
scripts/start_services.bat
```
或者手动运行（注意端口映射）：
```bash
# Qdrant 向量库
docker run -d -p 6333:6333 qdrant/qdrant
 
# Neo4j 图数据库
# 映射到 17474 (HTTP) 和 17687 (Bolt) 以避开 Windows 保留端口
docker run -d -p 17474:7474 -p 17687:7687 -e NEO4J_AUTH=neo4j/password neo4j
```

### 5. 启动服务
```bash
python server.py
# 服务启动后，浏览器将自动打开 http://localhost:38080
```

## 📂 实用工具

### PDF 智能切分
如果文档过大，可以使用内置脚本将其按页拆分（支持拖拽路径）：

```powershell
python scripts/split_pdf.py
```
-   支持 30 页/份自动切分。
-   自动处理 Windows 路径引号。

## 📂 项目结构

-   `server.py`: FastAPI 主程序及 API 接口 (包含后台任务管理)。
-   `core/`: 核心逻辑 (Parser, VectorStore, GraphStore, Config)。
-   `agents/`: LangGraph 节点 (GraphBuilder, RAG Router)。
-   `static/`: 前端静态资源 (Style 统一优化)。
-   `scripts/`: 实用脚本 (test_optimization.py, split_pdf.py)。

## 💡 使用指南

1.  **上传文档**: 拖拽 PDF 文件至上传区。系统会自动进行混合解析，提取实体并构建索引。
2.  **取消任务**: 上传过程中可随时取消，系统会自动清理已产生的脏数据。
3.  **专业问答**: 提出技术问题（例如：“LDMOS 器件的击穿电压是多少？”）。
4.  **图谱溯源**: 系统给出的每个论断都会链接到具体的文档和页码。

## 许可证
MIT