import streamlit as st
from core.parser import PDFParser
from core.vector_store import VectorStore
from agents.graph_builder import GraphBuilder
from graph_flow import run_workflow
from utils.gemini_client import GeminiClient
import base64
import tempfile
import os
import logging
from datetime import datetime

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
    st.session_state.processing_complete = False

# 侧边栏：文件上传和管理
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
    
    # 处理文件按钮
    if st.button("处理文件", key="process_button", disabled=not st.session_state.uploaded_files):
        with st.spinner("正在处理文件..."):
            logger.info(f"[处理流程] ========== 开始处理文件，共 {len(st.session_state.uploaded_files)} 个文件 ==========")
            
            # 处理每个上传的文件
            for file in st.session_state.uploaded_files:
                file_path = os.path.join(st.session_state.temp_dir, file.name)
                logger.info(f"[处理流程] ========== 开始处理文件: {file.name} ==========")
                
                # 1. 解析 PDF
                st.write(f"正在解析文件：{file.name}")
                logger.info(f"[步骤1-PDF解析] 开始解析PDF文件: {file_path}")
                document_blocks = parser.process_pdf(file_path, gemini_client)
                logger.info(f"[步骤1-PDF解析] PDF解析完成，提取到 {len(document_blocks)} 个文档块")
                
                # 记录每个块的详细内容
                logger.info(f"[步骤1-PDF解析] ========== 文档块详细内容 ==========")
                for idx, block in enumerate(document_blocks):
                    logger.info(f"[步骤1-PDF解析] 块 {idx+1} - 类型: {block['type']}, 页码: {block['page']}, 分级: {block['tier']}")
                    content = block.get('verified_content', block.get('content', ''))
                    logger.info(f"[步骤1-PDF解析] 块 {idx+1} 内容长度: {len(content)} 字符")
                    logger.info(f"[步骤1-PDF解析] 块 {idx+1} 内容预览: {content[:200]}...")
                    if 'coordinates' in block:
                        logger.info(f"[步骤1-PDF解析] 块 {idx+1} 坐标: {block['coordinates']}")
                logger.info(f"[步骤1-PDF解析] ========== 文档块详细内容结束 ==========")
                
                # 2. 构建知识图谱
                st.write(f"正在构建图谱：{file.name}")
                logger.info(f"[步骤2-图谱构建] 开始构建知识图谱")
                graph_stats = graph_builder.build_graph_from_blocks(document_blocks, file.name)
                logger.info(f"[步骤2-图谱构建] 图谱构建完成 - 处理块数: {graph_stats['processed_blocks']}, 创建实体数: {graph_stats['entities_created']}, 创建关系数: {graph_stats['relations_created']}")
                
                # 3. 将文档块添加到向量存储
                st.write(f"正在添加到向量库：{file.name}")
                logger.info(f"[步骤3-向量存储] 开始添加文档块到向量库")
                added_count = 0
                failed_count = 0
                for idx, block in enumerate(document_blocks):
                    try:
                        content = block.get('verified_content', block.get('content', ''))
                        logger.info(f"[步骤3-向量存储] 添加块 {idx+1} - 类型: {block['type']}, 页码: {block['page']}, 内容长度: {len(content)} 字符")
                        logger.debug(f"[步骤3-向量存储] 块 {idx+1} 完整内容: {content}")
                        
                        point_id = vector_store.add_document_block(block, file.name)
                        added_count += 1
                        logger.info(f"[步骤3-向量存储] 块 {idx+1} 添加成功 - 点ID: {point_id}")
                    except Exception as e:
                        failed_count += 1
                        logger.error(f"[步骤3-向量存储] 块 {idx+1} 添加失败: {str(e)}")
                logger.info(f"[步骤3-向量存储] 向量库添加完成，成功: {added_count}, 失败: {failed_count}, 总计: {len(document_blocks)}")
                
                # 获取向量库统计信息
                collection_info = vector_store.get_collection_info()
                logger.info(f"[步骤3-向量存储] 向量库统计 - 点数: {collection_info.get('points_count', 'N/A')}, 向量数: {collection_info.get('vectors_count', 'N/A')}")
                
                logger.info(f"[处理流程] ========== 文件 {file.name} 处理完成 ==========")
            
            # 标记处理完成
            st.session_state.processing_complete = True
            logger.info(f"[处理流程] ========== 所有文件处理完成 ==========")
            st.success("所有文件处理完成！")
    
    # 清除会话按钮
    if st.button("清除会话", key="clear_button"):
        # 清除会话状态
        st.session_state.uploaded_files = []
        st.session_state.chat_history = []
        st.session_state.processing_complete = False
        
        # 清除临时目录
        for file in os.listdir(st.session_state.temp_dir):
            os.remove(os.path.join(st.session_state.temp_dir, file))
        
        st.success("会话已清除！")

# 主界面：对话和 PDF 预览
col1, col2 = st.columns([2, 1])

# 左侧：对话界面
with col1:
    st.title("🧠 IC/BCD 多模态知识库系统")
    
    # 显示处理状态
    if st.session_state.processing_complete:
        st.success("文件处理完成，可以开始提问！")
    else:
        if st.session_state.uploaded_files:
            st.warning("请先点击'处理文件'按钮，处理完成后再提问！")
        else:
            st.info("请先上传 PDF 文件！")
    
    # 显示聊天历史
    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    
    # 输入框
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
                
                # 运行工作流
                result = run_workflow(prompt)
                logger.info(f"[问答流程] 工作流执行完成 - 审计通过: {result['audit_passed']}")
                
                # 显示回答
                st.markdown(result["generated_answer"])
                logger.info(f"[问答流程] 生成的回答长度: {len(result['generated_answer'])} 字符")
                
                # 显示审计结果
                if result["audit_passed"]:
                    st.success("✅ 回答已通过事实审计")
                    logger.info(f"[问答流程] 回答已通过事实审计")
                else:
                    st.error("❌ 回答未通过事实审计，已进行修正")
                    logger.warning(f"[问答流程] 回答未通过事实审计，已进行修正")
                
                # 添加助手消息到聊天历史
                st.session_state.chat_history.append({"role": "assistant", "content": result["generated_answer"]})
                logger.info(f"[问答流程] ========== 问题处理完成 ==========")

# 右侧：PDF 预览
with col2:
    st.title("📖 PDF 预览")
    
    if st.session_state.uploaded_files:
        # 选择要预览的文件
        selected_file = st.selectbox(
            "选择要预览的文件",
            [file.name for file in st.session_state.uploaded_files]
        )
        
        # 预览 PDF
        if selected_file:
            file_path = os.path.join(st.session_state.temp_dir, selected_file)
            
            # 读取 PDF 文件并转换为 Base64
            with open(file_path, "rb") as f:
                pdf_bytes = f.read()
            
            base64_pdf = base64.b64encode(pdf_bytes).decode("utf-8")
            pdf_display = f"<iframe src='data:application/pdf;base64,{base64_pdf}' width='100%' height='600' type='application/pdf'></iframe>"
            
            # 显示 PDF
            st.markdown(pdf_display, unsafe_allow_html=True)
    else:
        st.info("请先上传 PDF 文件！")

# 页脚
st.markdown("---")
st.markdown("📚 基于 LangGraph 的 IC/BCD 多模态知识库系统 | 2024")
