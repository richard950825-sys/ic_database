import streamlit as st
from core.parser import PDFParser
from core.vector_store import VectorStore
from core.graph_store import GraphStore
from agents.graph_builder import GraphBuilder
from graph_flow import run_workflow
from utils.gemini_client import GeminiClient
import base64
import tempfile
import os
import logging
import hashlib
from datetime import datetime

# ... (Previous imports remain, ensuring hashlib is at top)

# Function to calculate file hash
def get_file_hash(file_bytes):
    md5_hash = hashlib.md5()
    md5_hash.update(file_bytes)
    return md5_hash.hexdigest()

# ... (Logging setup remains)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app_monitor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 设置页面标题和布局
st.set_page_config(
    page_title="IC/BCD 多模态知识库系统",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 初始化各个模块
parser = PDFParser()
vector_store = VectorStore()
graph_store = GraphStore()
graph_builder = GraphBuilder()
gemini_client = GeminiClient()

# 创建临时目录用于存储上传的文件
if "temp_dir" not in st.session_state:
    st.session_state.temp_dir = tempfile.mkdtemp()

# 初始化会话状态
if "uploaded_files" not in st.session_state:
    st.session_state.uploaded_files = []

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

if "processing_complete" not in st.session_state:
    # Check if there are existing documents in the Knowledge Base
    try:
        existing_docs = graph_store.get_all_documents()
        if existing_docs:
            st.session_state.processing_complete = True
            logger.info("[App] Found existing documents in Knowledge Base. Enabling chat.")
        else:
            st.session_state.processing_complete = False
    except Exception as e:
        logger.error(f"[App] Failed to check for existing documents: {str(e)}")
        st.session_state.processing_complete = False

# 主界面：使用 Tab 分隔
tab_qa, tab_kb = st.tabs(["💬 智能对话", "📚 知识库管理"])

# Tab 1: 智能对话 (Original UI)
with tab_qa:
    col1, col2 = st.columns([2, 1])
    
    # 左侧：对话界面
    with col1:
        st.title("🧠 IC/BCD 多模态知识库系统")
        
        # 显示处理状态
        if st.session_state.processing_complete:
            st.success("文档就绪，可以开始提问！")
        else:
            if st.session_state.uploaded_files:
                st.warning("请先点击侧边栏'处理文件'按钮！")
            else:
                st.info("请先上传 PDF 文件，或确保知识库中已有文档。")
        
        # 显示聊天历史
        for message in st.session_state.chat_history:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
        
        # 输入框
        # 允许在有 Knowledge Base 数据的情况下直接提问（需改进逻辑，假设KB有数据即可）
        # 暂时保持 strict: processing_complete 必须为 True
        if prompt := st.chat_input("请输入您的问题...", disabled=not st.session_state.processing_complete):
            # 添加用户消息到聊天历史
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            
            # 显示用户消息
            with st.chat_message("user"):
                st.markdown(prompt)
            
            # 生成回答
            with st.chat_message("assistant"):
                with st.spinner("正在生成回答..."):
                    logger.info(f"[问答流程] ========== 开始处理用户问题 ==========")
                    logger.info(f"[问答流程] 用户问题: {prompt}")
                    
                    try:
                        # 运行工作流
                        result = run_workflow(prompt)
                        logger.info(f"[问答流程] 工作流执行完成 - 审计通过: {result['audit_passed']}")
                        
                        # 显示回答
                        st.markdown(result["generated_answer"])
                        
                        # 显示审计结果
                        if result["audit_passed"]:
                            st.success("✅ 回答已通过事实审计")
                        else:
                            st.error("❌ 回答未通过事实审计，已进行修正")
                        
                        # 添加助手消息到聊天历史
                        st.session_state.chat_history.append({"role": "assistant", "content": result["generated_answer"]})
                    except Exception as e:
                        st.error(f"生成回答时发生错误: {str(e)}")
                        logger.error(f"[问答流程] 错误: {str(e)}")

    # 右侧：PDF 预览
    with col2:
        st.title("📖 PDF 预览")
        if st.session_state.uploaded_files:
            selected_file = st.selectbox(
                "选择要预览的文件",
                [file.name for file in st.session_state.uploaded_files]
            )
            if selected_file:
                # Find the file object
                file_obj = next((f for f in st.session_state.uploaded_files if f.name == selected_file), None)
                if file_obj:
                    base64_pdf = base64.b64encode(file_obj.getvalue()).decode("utf-8")
                    pdf_display = f"<iframe src='data:application/pdf;base64,{base64_pdf}' width='100%' height='600' type='application/pdf'></iframe>"
                    st.markdown(pdf_display, unsafe_allow_html=True)
        else:
            st.info("预览仅对当前上传的文件有效")

# Tab 2: 知识库管理
with tab_kb:
    st.header("📚 知识库文档列表")
    if st.button("刷新列表"):
        st.rerun()
    
    docs = graph_store.get_all_documents()
    if docs:
        st.table(docs)
    else:
        st.info("知识库暂时为空")

# 侧边栏处理逻辑更新
with st.sidebar:
    st.title("📁 文件管理")
    
    # 文件上传
    uploaded_files = st.file_uploader(
        "上传 PDF 文件",
        type="pdf",
        accept_multiple_files=True
    )
    
    # 处理上传的文件
    if uploaded_files:
        for file in uploaded_files:
            if file not in st.session_state.uploaded_files:
                # 保存文件到临时目录
                file_path = os.path.join(st.session_state.temp_dir, file.name)
                logger.info(f"[文件上传] 开始保存文件: {file.name}, 大小: {file.size} bytes")
                with open(file_path, "wb") as f:
                    f.write(file.getvalue())
                logger.info(f"[文件上传] 文件保存成功: {file_path}")
                
                # 添加到会话状态
                st.session_state.uploaded_files.append(file)
                logger.info(f"[文件上传] 文件已添加到会话状态: {file.name}")
    
    # 显示已上传的文件
    if st.session_state.uploaded_files:
        st.subheader("已上传的文件")
        for file in st.session_state.uploaded_files:
            st.write(f"✅ {file.name}")
    
    if st.button("处理文件", key="process_button", disabled=not st.session_state.uploaded_files):
        with st.spinner("正在处理文件..."):
            logger.info(f"[处理流程] ========== 开始 ... ==========")
            
            processed_any = False
            
            for file in st.session_state.uploaded_files:
                file_bytes = file.getvalue()
                file_hash = get_file_hash(file_bytes)
                
                # Check Deduplication
                existing_doc = graph_store.get_document(file_hash)
                if existing_doc:
                    st.success(f"📄 {file.name} 已存在于知识库，无需重复处理 (Hash: {file_hash[:8]}...)")
                    logger.info(f"[处理流程] 文件跳过 (已存在): {file.name}")
                    continue
                
                # Process New File
                processed_any = True
                file_path = os.path.join(st.session_state.temp_dir, file.name)
                with open(file_path, "wb") as f:
                    f.write(file_bytes)
                
                # 1. Parse
                st.write(f"正在解析文件：{file.name}")
                document_blocks = parser.process_pdf(file_path, gemini_client)
                
                # 2. Graph
                st.write(f"正在构建图谱：{file.name}")
                graph_builder.build_graph_from_blocks(document_blocks, file.name)
                
                # 3. Vector
                st.write(f"正在添加到向量库：{file.name}")
                for block in document_blocks:
                    try:
                        vector_store.add_document_block(block, file.name)
                    except:
                        pass
                
                # 4. Save Metadata
                graph_store.add_document(
                    doc_hash=file_hash,
                    filename=file.name,
                    size=file.size,
                    upload_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                )
                logger.info(f"[处理流程] 文件处理完成并保存元数据: {file.name}")
            
            st.session_state.processing_complete = True
            st.success("处理流程结束！")
            st.rerun()


# 页脚
st.markdown("---")
st.markdown("📚 基于 LangGraph 的 IC/BCD 多模态知识库系统 | 2024")
