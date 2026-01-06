import os
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
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
import sys

# ... (Previous imports remain, ensuring hashlib is at top)

# Function to calculate file hash
def get_file_hash(file_bytes):
    md5_hash = hashlib.md5()
    md5_hash.update(file_bytes)
    return md5_hash.hexdigest()

# ... (Logging setup remains)
# Configure logging with explicit UTF-8 encoding
# Configure logging with explicit UTF-8 encoding
# Reset handlers to avoid duplication on Streamlit rerun
root_logger = logging.getLogger()
if root_logger.hasHandlers():
    root_logger.handlers.clear()
root_logger.setLevel(logging.INFO)

# File Handler with UTF-8
file_handler = logging.FileHandler('app_monitor.log', encoding='utf-8')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
root_logger.addHandler(file_handler)

# Stream Handler with UTF-8
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
root_logger.addHandler(stream_handler)
logger = logging.getLogger(__name__)

# Suppress noisy library logs
logging.getLogger("google_genai").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)

# 设置页面标题和布局
st.set_page_config(
    page_title="IC/BCD 多模态知识库系统",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for Gemini-like UI
st.markdown("""
<style>
    /* Global Settings - Light Theme */
    [data-testid="stAppViewContainer"] {
        background-color: #ffffff;
        color: #31333f;
    }
    
    /* Hide Header/Footer */
    header {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* Chat Container Styling */
    .stChatMessage {
        background-color: transparent;
        border: none;
        box-shadow: none;
    }

    /* User Message Specifics - Right Aligned */
    [data-testid="stChatMessage"]:nth-child(odd) {
        flex-direction: row-reverse;
        text-align: right;
    }
    
    /* Target the content container inside the chat message for background */
    [data-testid="stChatMessage"]:nth-child(odd) > div:first-child {
        background-color: #95ec69; /* WeChat Green for User */
        color: black;
        border-radius: 10px;
        padding: 10px;
        margin-right: 10px;
        margin-left: auto; /* Push to right */
        box-shadow: 0 1px 2px rgba(0,0,0,0.1);
    }

    /* Assistant Message - Left Aligned */
    [data-testid="stChatMessage"]:nth-child(even) {
        flex-direction: row;
        text-align: left;
    }

    [data-testid="stChatMessage"]:nth-child(even) > div:first-child {
        background-color: #ffffff;
        color: black;
        border-radius: 10px;
        padding: 10px;
        margin-left: 10px;
        margin-right: auto;
        box-shadow: 0 1px 2px rgba(0,0,0,0.1);
        border: 1px solid #e0e0e0;
    }
    
    /* Input Box Styling */
    .stChatInput {
        background-color: #f5f5f5;
        padding-bottom: 20px;
        border-top: 1px solid #ddd;
    }
    
    /* Enhance sidebar */
    [data-testid="stSidebar"] {
        background-color: #f8f9fa;
        border-right: 1px solid #e0e0e0;
    }
    
    /* Buttons */
    .stButton button {
        border-radius: 6px;
        transition: all 0.2s;
    }
    .stButton button:hover {
        transform: translateY(-1px);
        box-shadow: 0 2px 5px rgba(0,0,0,0.1);
    }

    /* Scrollbar */
    ::-webkit-scrollbar {
        width: 8px;
        height: 8px;
    }
    ::-webkit-scrollbar-track {
        background: #f1f1f1; 
    }
    ::-webkit-scrollbar-thumb {
        background: #ccc; 
        border-radius: 4px;
    }
    ::-webkit-scrollbar-thumb:hover {
        background: #bbb; 
    }
</style>
""", unsafe_allow_html=True)

# 初始化各个模块 (使用缓存避免重复初始化)
@st.cache_resource
def get_parser():
    return PDFParser()

@st.cache_resource
def get_vector_store():
    return VectorStore()

@st.cache_resource
def get_graph_store():
    return GraphStore()

@st.cache_resource
def get_graph_builder():
    return GraphBuilder()

@st.cache_resource
def get_gemini_client():
    return GeminiClient()

# 使用 Spinner 提示加载进度
with st.spinner("正在初始化系统组件，首次加载大型模型可能需要较长时间..."):
    parser = get_parser()
    
    # VectorStore 初始化包含 BGE-M3 模型加载 (约 2GB)，最耗时
    vector_store = get_vector_store()
    
    graph_store = get_graph_store()
    graph_builder = get_graph_builder()
    gemini_client = get_gemini_client()

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
        # 使用缓存的数据获取函数，避免每次刷新都查询数据库
        @st.cache_data(ttl=10) # 10s TTL because ingestion might change it
        def fetch_docs_status():
             return get_graph_store().get_all_documents()
        
        existing_docs = fetch_docs_status()
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
    # Use wider ratio for chat
    col1, col2 = st.columns([7, 3])
    
    # 左侧：对话界面
    with col1:
        st.title("🧠 IC/BCD 多模态知识库系统")
        
        # 显示处理状态 - Use toast instead of occupying space
        if not st.session_state.processing_complete:
            if st.session_state.uploaded_files:
                st.toast("请点击侧边栏'处理文件'按钮以开始对话", icon="⚠️")
            else:
                st.toast("请先上传并处理 PDF 文件", icon="ℹ️")
        
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
        with st.expander("📖 PDF 预览", expanded=False):
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

# Helper function to process a single file
def process_file(file_path, file_name, file_bytes):
    try:
        file_hash = get_file_hash(file_bytes)
        file_size = len(file_bytes)
        
        # 1. Parse
        st.toast(f"正在解析文件：{file_name}...", icon="🔄")
        # Check stop signal (though Streamlit rerun kills script, this is for manual checks if we used threads)
        
        document_blocks = parser.process_pdf(file_path, gemini_client)
        
        # 2. Graph
        st.toast(f"正在构建图谱：{file_name}...", icon="🕸️")
        graph_builder.build_graph_from_blocks(document_blocks, file_name)
        
        # 3. Vector
        st.toast(f"正在添加到向量库：{file_name}...", icon="💾")
        for block in document_blocks:
            try:
                vector_store.add_document_block(block, file_name)
            except Exception as e:
                logger.warning(f"Failed to add block to vector store: {e}")
        
        # 4. Save Metadata
        graph_store.add_document(
            doc_hash=file_hash,
            filename=file_name,
            size=file_size,
            upload_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        logger.info(f"[处理流程] 文件处理完成并保存元数据: {file_name}")
        st.toast(f"文件处理完成: {file_name}", icon="✅")
        return True
    
    except BaseException as e:
        # Catch ALL exceptions, including Streamlit's ScriptRunner stops/reruns
        logger.warning(f"[处理流程] 处理被中止或失败 {file_name}: {str(e)}")
        st.error(f"处理由于错误或用户中止而停止: {file_name}")
        
        # CLEANUP: Delete partial data
        logger.info(f"[处理流程] 正在清理已写入的数据: {file_name}")
        try:
            graph_store.delete_document(file_name)
            vector_store.delete_by_file_name(file_name)
            logger.info(f"[处理流程] 清理完成: {file_name}")
        except Exception as cleanup_error:
            logger.error(f"[处理流程] 清理失败: {cleanup_error}")
            
        # Re-raise unless it's a standard Exception we want to swallow (we don't)
        raise e

# ... (Sidebar remains largely similar, just calling process_file)

# Tab 2: 知识库管理
with tab_kb:
    st.header("📚 知识库文档列表")
    
    col_tools_1, col_tools_2 = st.columns([1, 4])
    with col_tools_1:
         if st.button("刷新列表"):
            st.rerun()
    
    docs = graph_store.get_all_documents()
    
    if not docs:
        st.info("知识库暂时为空")
    else:
        # Header
        cols = st.columns([3, 2, 2, 2, 2])
        cols[0].markdown("**文件名**")
        cols[1].markdown("**上传时间**")
        cols[2].markdown("**大小 (Bytes)**")
        cols[3].markdown("**状态**")
        cols[4].markdown("**操作**")
        st.markdown("---")
        
        for doc in docs:
            cols = st.columns([3, 2, 2, 2, 2])
            filename = doc.get('filename', 'Unknown')
            
            cols[0].write(filename)
            cols[1].write(doc.get('upload_time', 'N/A'))
            cols[2].write(doc.get('size', 0))
            cols[3].write(doc.get('status', 'Unknown'))
            
            with cols[4]:
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("🗑️", key=f"del_{filename}", help="删除文档"):
                        with st.spinner(f"正在删除 {filename}..."):
                            # Delete from Graph
                            graph_store.delete_document(filename)
                            # Delete from Vector
                            vector_store.delete_by_file_name(filename)
                            st.success(f"已删除 {filename}")
                            st.rerun()
                
                with c2:
                    if st.button("🔄", key=f"reprocess_{filename}", help="重新处理"):
                        # Check if file exists in temp dir
                        temp_path = os.path.join(st.session_state.temp_dir, filename)
                        if os.path.exists(temp_path):
                            with st.spinner(f"正在重新处理 {filename}..."):
                                # 1. Delete existing data
                                graph_store.delete_document(filename)
                                vector_store.delete_by_file_name(filename)
                                
                                # 2. Reprocess
                                with open(temp_path, "rb") as f:
                                    file_bytes = f.read()
                                
                                if process_file(temp_path, filename, file_bytes):
                                    st.success(f"重新处理完成: {filename}")
                                    st.rerun()
                        else:
                            st.error("源文件已丢失，请重新上传")

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
                safe_filename = os.path.basename(file.name)
                file_path = os.path.join(st.session_state.temp_dir, safe_filename)
                logger.info(f"[文件上传] 开始保存文件: {safe_filename}, 大小: {file.size} bytes")
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
        
        # 只显示处理按钮，移除容易引起混淆的中止按钮（建议使用右上角原生Stop）
        if st.button("开始处理文件", key="process_button", type="primary", use_container_width=True):
            with st.spinner("正在批量处理文件..."):
                logger.info(f"[处理流程] ========== 开始 ... ==========")
                
                processed_any = False
                
                status_container = st.status("正在处理文件...", expanded=True)
                
                for file in st.session_state.uploaded_files:
                    file_bytes = file.getvalue()
                    file_hash = get_file_hash(file_bytes)
                    
                    # Check Deduplication
                    existing_doc = graph_store.get_document(file_hash)
                    if existing_doc:
                        st.toast(f"📄 {file.name} 已存在，跳过")
                        status_container.write(f"Existing: {file.name}")
                        logger.info(f"[处理流程] 文件跳过 (已存在): {file.name}")
                        continue
                    
                    # Process New File
                    processed_any = True
                    status_container.write(f"Processing: {file.name}")
                    file_path = os.path.join(st.session_state.temp_dir, file.name)
                    
                    # Ensure file exists (it should, but just in case)
                    if not os.path.exists(file_path):
                         with open(file_path, "wb") as f:
                            f.write(file_bytes)
                    
                    process_file(file_path, file.name, file_bytes)
                
                st.session_state.processing_complete = True
                status_container.update(label="批量处理完成!", state="complete", expanded=False)
                st.success("批量处理结束！")
                if processed_any:
                    st.rerun()


# 页脚
st.markdown("---")
st.markdown("📚 基于 LangGraph 的 IC/BCD 多模态知识库系统 | 2024")
