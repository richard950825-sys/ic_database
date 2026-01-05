from utils.gemini_client import GeminiClient
from typing import List, Dict, Any

class DomainAnalyzer:
    def __init__(self):
        """
        初始化领域分析器
        """
        self.gemini_client = GeminiClient()
    
    def analyze_context(self, query: str, retrieved_contexts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        分析检索到的上下文，为生成回答做准备
        
        Args:
            query: 用户查询
            retrieved_contexts: 检索到的上下文列表
            
        Returns:
            分析结果，包含关键信息、上下文摘要等
        """
        # 准备上下文文本
        context_text = "\n\n".join([
            f"【来源：{ctx['metadata']['file_name']}，页码：{ctx['metadata']['page']}】\n{ctx['metadata']['content']}"
            for ctx in retrieved_contexts
        ])
        
        # 生成上下文摘要和关键信息提取
        analysis_prompt = f"""
        你是一位资深的 IC 设计和 BCD 工艺专家。请分析以下上下文，为回答用户问题做准备。
        
        用户问题：{query}
        
        上下文：
        {context_text}
        
        请完成以下任务：
        1. 提取与用户问题直接相关的关键信息
        2. 总结上下文的核心内容
        3. 识别上下文之间的关联关系
        4. 指出可能存在的信息缺口
        
        请按照以下格式输出：
        关键信息：
        - 信息点1
        - 信息点2
        ...
        
        上下文摘要：
        [简明扼要的摘要]
        
        上下文关联：
        - 关联1
        - 关联2
        ...
        
        信息缺口：
        [如果有信息缺口，列出；如果没有，写"无"]
        """
        
        analysis_result = self.gemini_client.generate_text(analysis_prompt, use_pro=True)
        
        # 解析分析结果
        lines = analysis_result.strip().split("\n")
        parsed_result = {
            "key_information": [],
            "context_summary": "",
            "context_relations": [],
            "information_gaps": "无"
        }
        
        current_section = None
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            if line == "关键信息：":
                current_section = "key_information"
            elif line == "上下文摘要：":
                current_section = "context_summary"
            elif line == "上下文关联：":
                current_section = "context_relations"
            elif line == "信息缺口：":
                current_section = "information_gaps"
            elif current_section == "key_information" and line.startswith("-"):
                parsed_result["key_information"].append(line[1:].strip())
            elif current_section == "context_summary":
                parsed_result["context_summary"] += line + "\n"
            elif current_section == "context_relations" and line.startswith("-"):
                parsed_result["context_relations"].append(line[1:].strip())
            elif current_section == "information_gaps":
                parsed_result["information_gaps"] = line
        
        return parsed_result
    
    def generate_answer(self, query: str, retrieved_contexts: List[Dict[str, Any]], analysis_result: Dict[str, Any]) -> str:
        """
        生成回答
        
        Args:
            query: 用户查询
            retrieved_contexts: 检索到的上下文列表
            analysis_result: 上下文分析结果
            
        Returns:
            生成的回答
        """
        # 准备上下文文本
        context_text = "\n\n".join([
            f"【来源：{ctx['metadata']['file_name']}，页码：{ctx['metadata']['page']}】\n{ctx['metadata']['content']}"
            for ctx in retrieved_contexts
        ])
        
        # 生成回答
        answer_prompt = f"""
        你是一位资深的 IC 设计和 BCD 工艺专家。请基于以下上下文，回答用户的问题。
        
        用户问题：{query}
        
        上下文：
        {context_text}
        
        上下文分析结果：
        关键信息：
        {"\n".join([f"- {info}" for info in analysis_result['key_information']])}
        
        上下文摘要：
        {analysis_result['context_summary']}
        
        上下文关联：
        {"\n".join([f"- {rel}" for rel in analysis_result['context_relations']])}
        
        信息缺口：
        {analysis_result['information_gaps']}
        
        请按照以下要求生成回答：
        1. 严格基于提供的上下文，不要添加任何外部信息
        2. 回答要准确、详细、专业
        3. 使用清晰的结构和格式
        4. 引用相关的上下文来源
        5. 对于数值、单位、专有名词等关键信息，要特别准确
        6. 如果上下文信息不足，明确说明
        
        请用中文回答。
        """
        
        answer = self.gemini_client.generate_text(answer_prompt, use_pro=True)
        
        return answer
    
    def format_answer_with_references(self, answer: str, retrieved_contexts: List[Dict[str, Any]]) -> str:
        """
        格式化回答，添加引用信息
        
        Args:
            answer: 生成的回答
            retrieved_contexts: 检索到的上下文列表
            
        Returns:
            格式化后的回答，包含引用信息
        """
        # 提取引用来源
        sources = []
        for i, ctx in enumerate(retrieved_contexts, 1):
            sources.append(
                f"[{i}] {ctx['metadata']['file_name']}，页码：{ctx['metadata']['page']}"
            )
        
        # 格式化回答
        formatted_answer = f"""
        {answer}
        
        ---
        
        **参考文献：**
        {"\n".join(sources)}
        """
        
        return formatted_answer
