from docling.document_converter import DocumentConverter
from docling.datamodel.document import DoclingDocument as Document
from typing import List, Dict, Any
import base64
import os
import logging

logger = logging.getLogger(__name__)

class PDFParser:
    def __init__(self):
        """
        初始化 PDF 解析器
        """
        self.converter = DocumentConverter()
        
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
                                logger.debug(f"[块提取] 处理GroupItem子元素，类型: {type(child).__name__}")
                                
                                # 检查子元素是否有type属性
                                if hasattr(child, 'type'):
                                    logger.debug(f"[块提取] 子元素type属性: {child.type}")
                                
                                # 处理不同类型的子元素
                                if hasattr(child, 'children'):
                                    # 如果子元素有children，递归处理
                                    process_group_item(child, page_num)
                                else:
                                    # 否则直接处理
                                    processed_block = self._process_block(child, page_num)
                                    if processed_block:
                                        blocks.append(processed_block)
                    
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
                
                processed_block = self._process_block(block, page_num)
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
                        processed_block = self._process_block(block, page_num)
                        if processed_block:
                            blocks.append(processed_block)
                elif hasattr(page_value, 'block'):
                    # 可能是单数形式
                    processed_block = self._process_block(page_value.block, page_num)
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
                                    processed_block = self._process_block(element, page_num)
                                    if processed_block:
                                        blocks.append(processed_block)
                                        content_found = True
                            else:
                                # 单个对象，直接处理
                                processed_block = self._process_block(content_value, page_num)
                                if processed_block:
                                    blocks.append(processed_block)
                                    content_found = True
                            
                            if content_found:
                                break
                    
                    if not content_found:
                        # 尝试将整个页面作为整体块处理
                        logger.debug(f"[块提取] 尝试将页面 {page_num} 作为整体块处理")
                        processed_block = self._process_block(page_value, page_num)
                        if processed_block:
                            blocks.append(processed_block)
        
        # 4. 尝试处理content属性
        elif hasattr(document, 'content'):
            # 尝试处理content属性
            logger.info(f"[块提取] 检测到content属性")
            logger.debug(f"[块提取] content 属性类型: {type(document.content)}")
            
            if isinstance(document.content, list):
                for item in document.content:
                    processed_block = self._process_block(item, 1)
                    if processed_block:
                        blocks.append(processed_block)
            else:
                processed_block = self._process_block(document.content, 1)
                if processed_block:
                    blocks.append(processed_block)
        else:
            logger.warning(f"[块提取] 未检测到blocks或pages属性，文档结构可能不支持")
        
        logger.info(f"[块提取] 块提取完成，共提取 {len(blocks)} 个块")
        return blocks
    
    def _process_block(self, block, page_num):
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
        
        for method_name, extractor in extraction_methods:
            try:
                content = extractor(block)
                if content and str(content).strip():
                    # 确保内容是字符串
                    if not isinstance(content, str):
                        content = str(content)
                    block_data["content"] = content
                    block_data["tier"] = self.classify_block(content)
                    content_found = True
                    logger.debug(f"[块处理] 使用{method_name}属性获取内容成功 - 页码: {page_num}, 内容长度: {len(content)}")
                    break
            except Exception as e:
                logger.debug(f"[块处理] 使用{method_name}属性获取内容失败: {str(e)}")
        
        # 如果还是没有找到内容，再根据块类型尝试特殊处理
        if not content_found:
            logger.debug(f"[块处理] 根据块类型 {block_type} 进行特殊处理")
            
            if block_type == "text":
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
            elif block_type == "table":
                # 表格块，提取表格内容
                if hasattr(block, 'rows'):
                    try:
                        table_content = []
                        for row in block.rows:
                            if hasattr(row, 'cells'):
                                row_content = [cell.text for cell in row.cells]
                                table_content.append(row_content)
                        if table_content:
                            # 将表格转换为文本格式
                            table_text = "\n".join(["\t".join(row) for row in table_content])
                            block_data["content"] = table_text
                            block_data["tier"] = "YELLOW"  # 表格默认为 YELLOW 级
                            content_found = True
                            logger.debug(f"[块处理] 表格块处理成功 - 页码: {page_num}, 行数: {len(table_content)}")
                    except Exception as e:
                        logger.warning(f"[块处理] 表格块处理失败: {str(e)}")
            elif block_type == "image":
                # 图像块，提取图像内容
                if hasattr(block, 'image') and block.image:
                    try:
                        # 获取图像的 Base64 编码
                        image_base64 = base64.b64encode(block.image).decode("utf-8")
                        block_data["content"] = image_base64
                        block_data["tier"] = "YELLOW"  # 图像默认为 YELLOW 级
                        content_found = True
                        logger.debug(f"[块处理] 图像块处理成功 - 页码: {page_num}")
                    except Exception as e:
                        logger.warning(f"[块处理] 图像块处理失败: {str(e)}")
        
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
    
    def tiered_qa_verification(self, blocks: List[Dict[str, Any]], gemini_client) -> List[Dict[str, Any]]:
        """
        对不同级别的块进行不同程度的 QA 验证
        
        Args:
            blocks: 文档块列表
            gemini_client: Gemini 客户端实例
            
        Returns:
            验证后的文档块列表
        """
        logger.info(f"[QA验证] 开始QA验证，共 {len(blocks)} 个块")
        verified_blocks = []
        
        tier_counts = {"RED": 0, "YELLOW": 0, "GREEN": 0}
        for block in blocks:
            tier = block.get("tier", "GREEN")
            tier_counts[tier] = tier_counts.get(tier, 0) + 1
        
        logger.info(f"[QA验证] 块分级统计 - RED: {tier_counts['RED']}, YELLOW: {tier_counts['YELLOW']}, GREEN: {tier_counts['GREEN']}")
        
        for idx, block in enumerate(blocks):
            # 确保 block 有 content 字段
            if "content" not in block:
                logger.warning(f"[QA验证] 块 {idx+1} 没有content字段，跳过")
                continue
            
            try:
                if block["tier"] == "RED":
                    # RED 块：调用 Gemini 1.5 Pro 进行两次互校
                    if block["type"] == "text":
                        logger.debug(f"[QA验证] RED块 {idx+1} 开始两次互校")
                        # 第一次解析
                        first_result = gemini_client.generate_text(
                            f"请准确解析以下 IC/BCD 工艺相关内容：\n{block['content']}",
                            use_pro=True
                        )
                        
                        # 第二次解析（不同的提示词）
                        second_result = gemini_client.generate_text(
                            f"请详细解读以下 IC/BCD 工艺参数：\n{block['content']}",
                            use_pro=True
                        )
                        
                        # 对比两次解析结果，确保一致性
                        if first_result.strip() == second_result.strip():
                            block["verified_content"] = first_result
                            block["verification_passed"] = True
                            logger.debug(f"[QA验证] RED块 {idx+1} 两次解析一致")
                        else:
                            # 如果不一致，进行第三次解析并取多数结果
                            logger.debug(f"[QA验证] RED块 {idx+1} 两次解析不一致，进行第三次解析")
                            third_result = gemini_client.generate_text(
                                f"请精确提取以下 IC/BCD 工艺信息：\n{block['content']}",
                                use_pro=True
                            )
                            
                            # 统计结果
                            results = [first_result, second_result, third_result]
                            result_counts = {result: results.count(result) for result in results}
                            majority_result = max(result_counts, key=result_counts.get)
                            
                            block["verified_content"] = majority_result
                            block["verification_passed"] = True
                
                elif block["tier"] == "YELLOW":
                    # YELLOW 块：单次解析
                    if block["type"] == "table":
                        logger.debug(f"[QA验证] YELLOW块 {idx+1} 表格解析")
                        # 表格转换为文本格式进行解析
                        table_text = "\n".join(["\t".join(row) for row in block["content"]])
                        verified_text = gemini_client.generate_text(
                            f"请准确解析以下工艺参数表格：\n{table_text}",
                            use_pro=True
                        )
                        block["verified_content"] = verified_text
                        block["verification_passed"] = True
                    elif block["type"] == "image":
                        logger.debug(f"[QA验证] YELLOW块 {idx+1} 图像描述生成")
                        # 图像生成描述
                        image_description = gemini_client.generate_multimodal(
                            prompt="请详细描述以下 IC/BCD 工艺相关图像的内容，包括结构、参数、特性等：",
                            image_base64=block["content"],
                            use_pro=True
                        )
                        block["verified_content"] = image_description
                        block["verification_passed"] = True
                    else:
                        # 其他 YELLOW 块类型，直接使用内容
                        logger.debug(f"[QA验证] YELLOW块 {idx+1} 直接使用内容")
                        block["verified_content"] = block["content"]
                        block["verification_passed"] = True
                
                elif block["tier"] == "GREEN":
                    # GREEN 块：直接通过验证
                    logger.debug(f"[QA验证] GREEN块 {idx+1} 直接通过验证")
                    block["verified_content"] = block["content"]
                    block["verification_passed"] = True
                
                verified_blocks.append(block)
            except Exception as e:
                # 处理异常，确保块有 verified_content 字段
                logger.error(f"[QA验证] 块 {idx+1} 验证失败: {str(e)}")
                block["verified_content"] = str(block["content"])
                block["verification_passed"] = False
                verified_blocks.append(block)
        
        logger.info(f"[QA验证] QA验证完成，成功验证 {len(verified_blocks)}/{len(blocks)} 个块")
        return verified_blocks
    
    def process_pdf(self, file_path: str, gemini_client) -> List[Dict[str, Any]]:
        """
        完整处理 PDF 文件的流程
        
        Args:
            file_path: PDF 文件路径
            gemini_client: Gemini 客户端实例
            
        Returns:
            处理后的文档块列表
        """
        logger.info(f"[PDF处理] ========== 开始处理PDF文件: {file_path} ==========")
        
        # 1. 解析 PDF
        document = self.parse_pdf(file_path)
        
        # 2. 提取文档块
        blocks = self.extract_document_blocks(document)
        
        # 3. 分级 QA 验证
        verified_blocks = self.tiered_qa_verification(blocks, gemini_client)
        
        logger.info(f"[PDF处理] ========== PDF处理完成，返回 {len(verified_blocks)} 个验证后的块 ==========")
        return verified_blocks
