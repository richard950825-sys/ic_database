# IC/BCD 多模态知识库系统

基于本地 PDF 上传的模拟 IC 设计和 BCD 工艺知识库系统，具备 100% 准确性、多策略检索、文档关系图谱以及分级质检功能。

## 技术栈

- **Language:** Python 3.12
- **Orchestration:** LangGraph
- **LLM API:** Google Gemini 3 Pro Preview (用于复杂推理与审计)
- **LLM API:** Google Gemini 2.5 Flash / Pro (全栈接管：推理、审计、路由、生成)
- **PDF Parsing:** Docling v2 (IBM) - 支持 CUDA 加速
- **Databases:** 
  - Qdrant (向量存储)
  - Neo4j (知识图谱)
- **GUI:** Streamlit

## 系统架构

### 模块 A: 分级多模态解析流水线 (Intelligent Multimodal Ingestion)
1.  **Layout Analysis (Docling):** 
    - 语义分割文档块 (Text, Table, Image)。
    - 优先处理 Table 和 Image 块，防止被误识别为普通文本。
2.  **Tiered Tagging (分级标记):** 
    - **RED (关键数据):** 包含击穿电压、工艺参数、Design Rule 等核心指标。
    - **YELLOW (结构化/视觉数据):** 表格、电路图、截面图。
    - **GREEN (通用信息):** 摘要、背景描述。
3.  **Tiered QA Verification (分级质检):**
    - **RED:** 双重互校 (Dual-Model Check)。使用 Gemini 3 Pro 进行两轮独立解析，不一致则进行第三轮仲裁。
    - **YELLOW:** 专家模型重构。
        - **Table Specialist:** 将表格转换为 Markdown 并提取层级关系。
        - **Vision Interpreter:** 生成图像的工程化语义描述。
    - **GREEN:** 直通 (Pass-through)，保留原始 OCR 结果。

### 模块 B: 意图路由与多策略检索 (GraphRAG Integration)
1.  **Graph Construction:** 提取实体 (Entity) 及关系 (Relation)，构建 Neo4j 图谱，实现跨文档关联。
2.  **Vector Store:** 存储文本块和图像描述的 Embedding (Gemini text-embedding-004)。
3.  **Query Router:** 根据用户意图 (FACTUAL, RELEASE_CHECK, etc.) 路由至精确匹配、图谱探索或语义搜索。

### 模块 C: UI 与持久化
- **Session Persistence:** 自动检测数据库状态，重启后保留 Chat Input 激活状态。
- **Deduplication:** 基于文件 Hash (MD5) 的上传去重机制。

## 快速开始

### 1. 环境配置

#### Python 环境
需要 Python 3.12+。
```bash
# 创建虚拟环境
python -m venv venv
# 激活环境 (Windows)
.\venv\Scripts\Activate.ps1
# 安装依赖
pip install -r requirements.txt
```

#### 配置环境变量
```bash
cp .env.example .env
# 编辑 .env 文件，填写 Google API Key, Neo4j, Qdrant 配置
```

### 2. 启动数据库

#### Qdrant (向量库)
```bash
docker run -d -p 6333:6333 -p 6334:6334 qdrant/qdrant
```

#### Neo4j (图数据库)
```bash
docker run -d -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/password neo4j
```
*注意：首次登录 http://localhost:7474 修改密码，并确保与 `.env` 中一致。*



### 4. 启动应用
```bash
streamlit run app.py
```

## 核心功能

1.  **分级解析与验证**: 利用 Gemini 3 Pro 的强推理能力，对关键数据进行多轮验证，确保 100% 准确率。
2.  **表格/图像深度理解**: 专门的 Table Specialist 将 PDF 表格还原为结构化 Markdown，解决传统 OCR 对复杂表格处理不佳的问题。
3.  **知识图谱关联**: 自动发现文档间的实体关系（如“Foundry” -> “Process Node”）。
4.  **智能交互**: Streamlit 界面支持文件上传、进度实时反馈、自动去重及持久化会话。

## 配置说明 (.env)

| 变量名 | 说明 |
|--------|------|
| `GOOGLE_API_KEY` | Gemini API 密钥 (必须) |
| `NEO4J_URI` | `bolt://localhost:7687` |
| `NEO4J_USERNAME` | `neo4j` |
| `NEO4J_PASSWORD` | 数据库密码 |
| `QDRANT_URL` | `http://localhost:6333` |
| `EMBEDDING_MODEL` | `models/text-embedding-004` |
| `LLM_MODEL` | `gemini-3-pro-preview` |

## 贡献
欢迎提交 Issue 和 Pull Request！

## 许可证
MIT