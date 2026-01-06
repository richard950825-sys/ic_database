from docling.document_converter import DocumentConverter
from docling.datamodel.document import DoclingDocument as Document
from typing import List, Dict, Any
import base64
import os
import logging

import logging
from docling_core.types.doc import TableItem, PictureItem, TextItem

logger = logging.getLogger(__name__)

class PDFParser:
    def __init__(self):
        """
        初始化 PDF 解析器
        """
        from core.config import settings
        from docling.datamodel.pipeline_options import PdfPipelineOptions, AcceleratorOptions, AcceleratorDevice
        
        pipeline_options = PdfPipelineOptions()
        pipeline_options.accelerator_options = AcceleratorOptions(
            num_threads=4, device=AcceleratorDevice.CUDA
        )
        # Hybrid Parsing: 
        # If USE_OCR=False, we skip dense OCR. Native text is extracted directly.
        # Images (including scanned tables) are handled by Multimodal LLM later.
        pipeline_options.do_ocr = settings.USE_OCR
        pipeline_options.do_table_structure = True
        pipeline_options.table_structure_options.do_cell_matching = True
        pipeline_options.generate_picture_images = True  # Ensure images are generated
        
        from docling.datamodel.base_models import InputFormat
        from docling.document_converter import PdfFormatOption
        
        self.converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
            }
        )
        
        # 定义分级标签的关键词
        self.tier_keywords = {
            "RED": ["Breakdown Voltage", "DRC", "LDMOS", "M3", "MIM", "CMOS", "BCD", "工艺参数", "设计规则", "击穿电压", "漏电流"],
            "YELLOW": ["Table", "图", "示意图", "流程图", "参数表", "特性曲线"],
            "GREEN": ["摘要", "引言", "背景", "参考文献", "致谢"]
        }
    
    def parse_pdf(self, file_path: str) -> Document:
        """
        解析 PDF 文件
        
        Args:
            file_path: PDF 文件路径
            
        Returns:
            解析后的文档对象
        """
        logger.info(f"[PDF解析] 开始解析文件: {file_path}")
        result = self.converter.convert(file_path)
        document = result.document
        logger.info(f"[PDF解析] 文件解析成功，文档类型: {type(document)}")
        return document
    
    def classify_block(self, block_content: str) -> str:
        """
        对文档块进行分级标签
        
        Args:
            block_content: 文档块内容
            
        Returns:
            分级标签：RED、YELLOW 或 GREEN
        """
        # 优先检查 RED 关键词
        for keyword in self.tier_keywords["RED"]:
            if keyword in block_content:
                return "RED"
        
        # 然后检查 YELLOW 关键词
        for keyword in self.tier_keywords["YELLOW"]:
            if keyword in block_content:
                return "YELLOW"
        
        # 默认标记为 GREEN
        return "GREEN"
    
    def extract_document_blocks(self, document) -> List[Dict[str, Any]]:
        """
        从文档中提取块，并进行分级标签
        
        Args:
            document: 解析后的文档对象
            
        Returns:
            文档块列表，每个块包含内容、类型、页码、坐标和分级标签
        """
        logger.info(f"[块提取] 开始提取文档块")
        blocks = []
        
        # 打印文档对象的所有属性，用于调试
        logger.debug(f"[块提取] 文档对象类型: {type(document)}")
        logger.debug(f"[块提取] 文档对象属性: {[attr for attr in dir(document) if not attr.startswith('_')]}")
        
        # 检查文档结构，处理不同的 docling API 版本
        
        # 1. 首先检查文档的body属性（这是docling的新结构）
        if hasattr(document, 'body'):
            logger.info(f"[块提取] 检测到body属性，类型: {type(document.body)}")
            
            # 处理GroupItem类型的body
            from docling_core.types.doc.document import GroupItem
            if isinstance(document.body, GroupItem):
                logger.info(f"[块提取] 检测到GroupItem类型的body，开始处理其内容")
                
                # 查看GroupItem的结构
                logger.debug(f"[块提取] GroupItem属性: {[attr for attr in dir(document.body) if not attr.startswith('_')]}")
                
                # 处理GroupItem的children
                if hasattr(document.body, 'children'):
                    logger.info(f"[块提取] GroupItem有children属性")
                    
                    # 递归处理GroupItem的children
                    def process_group_item(group_item, page_num=1):
                        """递归处理GroupItem的children"""
                        if hasattr(group_item, 'children'):
                            for child in group_item.children:
                                # logger.debug(f"[块提取] 处理GroupItem子元素，类型: {type(child).__name__}")
                                
                                
                                # 尝试解析 RefItem
                                if hasattr(child, 'resolve'):
                                    try:
                                        resolved_child = child.resolve(document)
                                        if resolved_child:
                                            # logger.debug(f"[块提取] RefItem解析为: {type(resolved_child).__name__}")
                                            child = resolved_child
                                    except Exception as e:
                                        logger.warning(f"[块提取] 解析RefItem失败: {str(e)}")
                                
                                # 检查子元素是否有type属性
                                if hasattr(child, 'type'):
                                    # logger.debug(f"[块提取] 子元素type属性: {child.type}")
                                    pass
                                
                                # 尝试从元素中提取页码
                                current_page = page_num
                                if hasattr(child, 'prov') and child.prov:
                                    # 尝试获取第一页
                                    try:
                                        if hasattr(child.prov, 'page_no'):
                                            current_page = child.prov.page_no
                                        elif isinstance(child.prov, list) and len(child.prov) > 0:
                                            current_page = child.prov[0].page_no
                                    except:
                                        pass
                                
                                # logic change: Try to process as a block FIRST
                                processed_block = self._process_block(child, current_page, document)
                                if processed_block:
                                    blocks.append(processed_block)
                                    # If processed successfully (has content), do not recurse into its children (e.g. spans)
                                    continue
                                
                                # If not processed (e.g. GroupItem with no direct content), recurse if it has children
                                if hasattr(child, 'children'):
                                    process_group_item(child, current_page)
                    
                    process_group_item(document.body)
        
        # 2. 检查文档的blocks属性
        elif hasattr(document, 'blocks'):
            # 新的 API 结构：文档直接包含 blocks
            logger.info(f"[块提取] 检测到新的API结构，文档直接包含blocks")
            logger.debug(f"[块提取] blocks 属性类型: {type(document.blocks)}")
            logger.debug(f"[块提取] blocks 数量: {len(document.blocks)}")
            
            for block in document.blocks:
                # 检查块是否有页面信息
                if hasattr(block, 'page'):
                    page_num = block.page + 1  # 转换为从1开始的页码
                else:
                    page_num = 1  # 默认页码为1
                
                processed_block = self._process_block(block, page_num, document)
                if processed_block:
                    blocks.append(processed_block)
        
        # 3. 检查文档的pages属性
        elif hasattr(document, 'pages'):
            # 旧的 API 结构：文档包含 pages
            logger.info(f"[块提取] 检测到旧的API结构，文档包含pages")
            logger.debug(f"[块提取] pages 属性类型: {type(document.pages)}")
            logger.debug(f"[块提取] pages 数量: {len(document.pages)}")
            
            # 处理 pages 可能是字典或列表的情况
            pages_items = []
            if isinstance(document.pages, dict):
                # pages 是字典，使用 items() 获取键值对
                logger.debug(f"[块提取] pages 是字典，键: {list(document.pages.keys())}")
                pages_items = list(document.pages.items())
            else:
                # pages 是列表，使用 enumerate() 获取索引和值
                pages_items = list(enumerate(document.pages))
            
            for page_key, page_value in pages_items:
                # 确定页码
                if isinstance(page_key, int):
                    page_num = page_key + 1  # 索引从0开始，页码从1开始
                else:
                    # 尝试从page_key中提取数字作为页码
                    try:
                        page_num = int(page_key) + 1
                    except (ValueError, TypeError):
                        page_num = 1  # 默认页码为1
                
                logger.debug(f"[块提取] 页面 {page_num} 类型: {type(page_value)}")
                logger.debug(f"[块提取] 页面 {page_num} 属性: {[attr for attr in dir(page_value) if not attr.startswith('_')]}")
                
                # 如果 page_value 是整数，跳过
                if isinstance(page_value, (int, str)):
                    logger.debug(f"[块提取] 页面值是 {type(page_value)}，跳过")
                    continue
                
                # 检查页面是否有 blocks 属性
                if hasattr(page_value, 'blocks'):
                    logger.debug(f"[块提取] 页面 {page_num} 包含 {len(page_value.blocks)} 个块")
                    for block in page_value.blocks:
                        processed_block = self._process_block(block, page_num, document)
                        if processed_block:
                            blocks.append(processed_block)
                elif hasattr(page_value, 'block'):
                    # 可能是单数形式
                    processed_block = self._process_block(page_value.block, page_num, document)
                    if processed_block:
                        blocks.append(processed_block)
                else:
                    # 检查是否有其他可能的内容属性
                    content_found = False
                    for content_attr in ['elements', 'content', 'body', 'items', 'children']:
                        if hasattr(page_value, content_attr):
                            content_value = getattr(page_value, content_attr)
                            logger.debug(f"[块提取] 页面 {page_num} 有 {content_attr} 属性，类型: {type(content_value)}")
                            
                            if hasattr(content_value, '__iter__') and not isinstance(content_value, (str, bytes)):
                                # 可迭代对象，遍历每个元素
                                for element in content_value:
                                    processed_block = self._process_block(element, page_num, document)
                                    if processed_block:
                                        blocks.append(processed_block)
                                        content_found = True
                            else:
                                # 单个对象，直接处理
                                processed_block = self._process_block(content_value, page_num, document)
                                if processed_block:
                                    blocks.append(processed_block)
                                    content_found = True
                            
                            if content_found:
                                break
                    
                    if not content_found:
                        # 尝试将整个页面作为整体块处理
                        logger.debug(f"[块提取] 尝试将页面 {page_num} 作为整体块处理")
                        processed_block = self._process_block(page_value, page_num, document)
                        if processed_block:
                            blocks.append(processed_block)
        
        # 4. 尝试处理content属性
        elif hasattr(document, 'content'):
            # 尝试处理content属性
            logger.info(f"[块提取] 检测到content属性")
            logger.debug(f"[块提取] content 属性类型: {type(document.content)}")
            
            if isinstance(document.content, list):
                for item in document.content:
                    processed_block = self._process_block(item, 1, document)
                    if processed_block:
                        blocks.append(processed_block)
            else:
                processed_block = self._process_block(document.content, 1, document)
                if processed_block:
                    blocks.append(processed_block)
        else:
            logger.warning(f"[块提取] 未检测到blocks或pages属性，文档结构可能不支持")
        
        logger.info(f"[块提取] 块提取完成，共提取 {len(blocks)} 个块")
        return blocks
    
    def _process_block(self, block, page_num, document):
        """
        处理单个块并返回处理后的块数据
        
        Args:
            block: 块对象
            page_num: 页码
            
        Returns:
            处理后的块数据，如果无法处理则返回 None
        """
        logger.debug(f"[块处理] 开始处理块 - 页码: {page_num}")
        logger.debug(f"[块处理] 块对象类型: {type(block)}")
        logger.debug(f"[块处理] 块对象属性: {[attr for attr in dir(block) if not attr.startswith('_')]}")
        
        block_type = getattr(block, 'type', 'unknown')
        
        # 更鲁棒的坐标提取，处理bbox可能不存在的情况
        x1 = getattr(block, 'x1', 0)
        y1 = getattr(block, 'y1', 0)
        x2 = getattr(block, 'x2', 0)
        y2 = getattr(block, 'y2', 0)
        
        # 尝试从bbox属性获取坐标
        if hasattr(block, 'bbox'):
            bbox = block.bbox
            x1 = getattr(bbox, 'x1', x1)
            y1 = getattr(bbox, 'y1', y1)
            x2 = getattr(bbox, 'x2', x2)
            y2 = getattr(bbox, 'y2', y2)
        
        block_data = {
            "type": block_type,
            "page": page_num,
            "coordinates": {
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2
            }
        }
        
        # 直接跳过根据块类型处理内容的部分，先尝试通用内容提取方式
        content_found = False
        
        # 优先处理特定类型的块 (TableItem, PictureItem)，避免被通用的 text 属性捕获
        if isinstance(block, TableItem) or block_type == "table":
            # 表格块，优先尝试 export_to_markdown
            try:
                table_text = ""
                if hasattr(block, 'export_to_markdown'):
                    table_text = block.export_to_markdown(document)
                    logger.debug(f"[块处理] 使用 export_to_markdown 提取表格成功")
                elif hasattr(block, 'rows'):
                    # 旧逻辑兼容
                    table_content = []
                    for row in block.rows:
                        if hasattr(row, 'cells'):
                            row_content = [cell.text for cell in row.cells]
                            table_content.append(row_content)
                    if table_content:
                        table_text = "\n".join(["\t".join(row) for row in table_content])
                
                if table_text.strip():
                    block_data["content"] = table_text
                    block_data["tier"] = "YELLOW"  # 强制标记为 YELLOW 以触发 Table Specialist
                    block_data["type"] = "table"   # 确保类型正确
                    content_found = True
                    logger.debug(f"[块处理] 表格块处理成功 (优先) - 页码: {page_num}")
            except Exception as e:
                logger.warning(f"[块处理] 表格块优先处理失败: {str(e)}")

        if not content_found and (isinstance(block, PictureItem) or block_type == "image"):
            # 图像块，提取图像内容
            try:
                # 获取图像的 Base64 编码
                from docling_core.types.doc import ImageRefMode
                image_base64 = None
                
                # 情况1: block.image 是 ImageRef，有 uri 且是 data uri
                if hasattr(block, 'image') and hasattr(block.image, 'uri') and block.image.uri:
                    uri_str = str(block.image.uri)
                    if uri_str.startswith('data:image'):
                        image_base64 = uri_str.split(',')[1]
                
                # 情况2: block.image 是 bytes (可能是旧版本或特定情况)
                elif hasattr(block, 'image') and isinstance(block.image, bytes):
                    image_base64 = base64.b64encode(block.image).decode("utf-8")
                
                # 情况3: 使用 get_image 方法 (需要 document)
                elif hasattr(block, 'get_image') and document:
                    try:
                        pil_image = block.get_image(document)
                        if pil_image:
                            # 转换为 base64
                            from io import BytesIO
                            buffered = BytesIO()
                            pil_image.save(buffered, format="PNG")
                            image_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
                    except Exception as e:
                        logger.debug(f"[块处理] get_image 失败: {e}")

                if image_base64:
                    block_data["content"] = image_base64
                    block_data["tier"] = "YELLOW"
                    block_data["type"] = "image"
                    content_found = True
                    logger.debug(f"[块处理] 图像块处理成功 (优先) - 页码: {page_num}")
            except Exception as e:
                logger.warning(f"[块处理] 图像块优先处理失败: {str(e)}")

        # 优先尝试多种内容提取方式，不依赖于块类型
        logger.debug(f"[块处理] 尝试多种内容提取方式，块类型: {block_type}")
        
        # 扩展的内容提取方式列表
        extraction_methods = [
            ('text', lambda b: getattr(b, 'text', None)),
            ('content', lambda b: getattr(b, 'content', None)),
            ('text_content', lambda b: getattr(b, 'text_content', None)),
            ('full_text', lambda b: getattr(b, 'full_text', None)),
            ('body', lambda b: str(getattr(b, 'body', None))),
            ('paragraphs', lambda b: "".join([p.text for p in b.paragraphs]) if hasattr(b, 'paragraphs') else None),
            ('lines', lambda b: "".join([line.text for line in b.lines]) if hasattr(b, 'lines') else None),
            ('string_value', lambda b: getattr(b, 'string_value', None)),
            ('value', lambda b: getattr(b, 'value', None)),
            ('data', lambda b: getattr(b, 'data', None)),
        ]
        
        if not content_found:
            for method_name, extractor in extraction_methods:
                try:
                    content = extractor(block)
                    if content and str(content).strip():
                        # 确保内容是字符串
                        if not isinstance(content, str):
                            content = str(content)
                        block_data["content"] = content
                        block_data["tier"] = self.classify_block(content)
                        
                        # Update type if it was unknown and we found text
                        if block_data["type"] == "unknown" and method_name in ['text', 'content', 'text_content', 'full_text', 'paragraphs', 'lines', 'string_value']:
                            block_data["type"] = "text"
                        
                        content_found = True
                        logger.debug(f"[块处理] 使用{method_name}属性获取内容成功 - 页码: {page_num}, 内容长度: {len(content)}")
                        break
                except Exception as e:
                    logger.debug(f"[块处理] 使用{method_name}属性获取内容失败: {str(e)}")
        
        # 如果还是没有找到内容，再根据块类型尝试特殊处理 (Fallback for Text)
        if not content_found:
            logger.debug(f"[块处理] 根据块类型 {block_type} 进行特殊处理 (Fallback)")
            
            # 使用 isinstance 检查类型，更健壮
            if isinstance(block, TextItem) or block_type == "text":
                # 文本块，提取文本内容
                if hasattr(block, 'lines'):
                    try:
                        text_content = "".join([line.text for line in block.lines])
                        if text_content.strip():
                            block_data["content"] = text_content
                            block_data["tier"] = self.classify_block(text_content)
                            content_found = True
                            logger.debug(f"[块处理] 文本块处理成功 - 页码: {page_num}, 内容长度: {len(text_content)}")
                    except Exception as e:
                        logger.warning(f"[块处理] 文本块处理失败: {str(e)}")
        
        # 最终兜底：尝试将整个块转换为字符串
        if not content_found:
            try:
                block_str = str(block)
                if block_str.strip() and len(block_str) > 10:  # 降低长度要求，确保更多块能被处理
                    block_data["content"] = block_str
                    block_data["tier"] = "GREEN"  # 默认级别
                    content_found = True
                    logger.debug(f"[块处理] 使用块字符串表示获取内容成功 - 页码: {page_num}")
                else:
                    logger.debug(f"[块处理] 块字符串太短或无意义 - 长度: {len(block_str)}")
            except Exception as e:
                logger.warning(f"[块处理] 块字符串转换失败: {str(e)}")
        
        # 只有当找到内容时，才返回块数据
        if content_found:
            logger.debug(f"[块处理] 块处理成功 - 页码: {page_num}, 类型: {block_type}")
            return block_data
        else:
            logger.warning(f"[块处理] 块处理失败，未找到内容 - 页码: {page_num}, 类型: {block_type}")
            return None
    
    def _verify_single_block(self, block, idx, gemini_client):
        """
        验证单个块的逻辑，用于并行处理
        """
        # 确保 block 有 content 字段
        if "content" not in block:
            # logger.warning(f"[QA验证] 块 {idx+1} 没有content字段，跳过")
            return block
        
        try:
            if block["tier"] == "RED":
                # RED 块：优化为单次高质量解析，减少 API 调用和耗时
                if block["type"] == "text":
                    logger.debug(f"[QA验证] RED块 {idx+1} 开始解析 (优化模式)")
                    # 使用更明确的 Prompt，单次调用即可
                    verified_text = gemini_client.generate_text(
                        f"作为 IC/BCD 工艺专家，请准确解析并修正以下技术内容的表述，提取关键参数：\n{block['content']}",
                        use_pro=True
                    )
                    block["verified_content"] = verified_text
                    block["verification_passed"] = True
            
            elif block["tier"] == "YELLOW":
                # YELLOW 块：保持单次解析
                if block["type"] == "table":
                    logger.debug(f"[QA验证] YELLOW块 {idx+1} 表格解析")
                    table_markdown = block["content"]
                    verified_text = gemini_client.generate_text(
                        f"请准确解析以下工艺参数表格(Markdown格式)，提取关键参数和层级关系：\n{table_markdown}",
                        use_pro=True
                    )
                    block["verified_content"] = verified_text
                    block["verification_passed"] = True
                elif block["type"] == "image":
                    logger.debug(f"[QA验证] YELLOW块 {idx+1} 图像描述生成")
                    # Hybrid Strategy: Since OCR is disabled, scanned tables appear as images.
                    # We expressly ask the LLM to output Markdown if it sees a table.
                    image_description = gemini_client.generate_multimodal(
                        prompt="请分析这张 IC/BCD 工艺相关的图片。\n1. 如果图片是表格（包含有线或无线的表结构），请务必将其转换为 Markdown 表格格式输出。\n2. 如果是电路图、截面图或示意图，请详细描述其结构、关键参数和特性。\n3. 如果是普通文本截图，请提取其中的文字内容。",
                        image_base64=block["content"],
                        use_pro=True
                    )
                    block["verified_content"] = image_description
                    block["verification_passed"] = True
                else:
                    block["verified_content"] = block["content"]
                    block["verification_passed"] = True
            
            elif block["tier"] == "GREEN":
                # GREEN 块：直接通过
                block["verified_content"] = block["content"]
                block["verification_passed"] = True
            
        except Exception as e:
            logger.error(f"[QA验证] 块 {idx+1} 验证失败: {str(e)}")
            block["verified_content"] = str(block.get("content", ""))
            block["verification_passed"] = False
            
        return block

    
    def process_pdf(self, file_path: str, gemini_client, progress_callback=None) -> List[Dict[str, Any]]:
        """
        完整处理 PDF 文件的流程
        
        Args:
            file_path: PDF 文件路径
            gemini_client: Gemini 客户端实例
            progress_callback: 进度回调函数 callback(current, total, msg)
            
        Returns:
            处理后的文档块列表
        """
        logger.info(f"[PDF处理] ========== 开始处理PDF文件: {file_path} ==========")
        
        if progress_callback: progress_callback(0, 0, "正在解析 PDF 结构...")

        # 1. 解析 PDF
        document = self.parse_pdf(file_path)
        
        # 2. 提取文档块
        blocks = self.extract_document_blocks(document)
        
        # 3. 分级 QA 验证
        if progress_callback: progress_callback(0, len(blocks), "开始 QA 验证...")
        verified_blocks = self.tiered_qa_verification(blocks, gemini_client, progress_callback)
        
        logger.info(f"[PDF处理] ========== PDF处理完成，返回 {len(verified_blocks)} 个验证后的块 ==========")
        return verified_blocks

    def tiered_qa_verification(self, blocks: List[Dict[str, Any]], gemini_client, progress_callback=None) -> List[Dict[str, Any]]:
        """
        对不同级别的块进行不同程度的 QA 验证 (并行优化版)
        """
        total_blocks = len(blocks)
        logger.info(f"[QA验证] 开始QA验证，共 {total_blocks} 个块 (并行模式)")
        
        tier_counts = {"RED": 0, "YELLOW": 0, "GREEN": 0}
        for block in blocks:
            tier = block.get("tier", "GREEN")
            tier_counts[tier] = tier_counts.get(tier, 0) + 1
        
        logger.info(f"[QA验证] 块分级统计 - RED: {tier_counts['RED']}, YELLOW: {tier_counts['YELLOW']}, GREEN: {tier_counts['GREEN']}")
        
        # 使用 ThreadPoolExecutor 进行并行处理
        from concurrent.futures import ThreadPoolExecutor
        import concurrent.futures
        
        verified_blocks = []
        # 限制并发数
        max_workers = 5
        
        processed_count = 0

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            future_to_idx = {
                executor.submit(self._verify_single_block, block, i, gemini_client): i 
                for i, block in enumerate(blocks)
            }
            
            # 收集结果
            for future in concurrent.futures.as_completed(future_to_idx):
                idx = future_to_idx[future]
                processed_count += 1
                try:
                    result_block = future.result()
                    verified_blocks.append((idx, result_block))
                except Exception as e:
                    logger.error(f"[QA验证] 线程执行异常 (块 {idx}): {e}")
                    # Fallback
                    block = blocks[idx]
                    block["verified_content"] = str(block.get("content", ""))
                    verified_blocks.append((idx, block))
                
                # Update progress
                if progress_callback:
                    progress_callback(processed_count, total_blocks, f"验证块 {idx+1}")

        # 恢复原始顺序
        verified_blocks.sort(key=lambda x: x[0])
        verified_blocks = [b[1] for b in verified_blocks]
        
        logger.info(f"[QA验证] QA验证完成，处理 {len(verified_blocks)} 个块")
        return verified_blocks

