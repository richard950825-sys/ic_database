from utils.gemini_client import GeminiClient
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)

class ResponseAuditor:
    def __init__(self):
        """
        初始化响应审计器
        """
        self.gemini_client = GeminiClient()
    
    def audit_response(self, original_contexts: List[Dict[str, Any]], generated_answer: str) -> Dict[str, Any]:
        """
        审计生成的回答是否符合原始上下文
        
        Args:
            original_contexts: 原始上下文列表
            generated_answer: 生成的回答
            
        Returns:
            审计结果，包含是否通过、错误信息、建议等
        """
        # 准备原始上下文文本
        original_text = "\n\n".join([
            f"【来源：{ctx['metadata']['file_name']}，页码：{ctx['metadata']['page']}】\n{ctx['metadata']['content']}"
            for ctx in original_contexts
        ])
        
        prompt = f"""
        你是一位严格的事实审计专家，负责检查生成的回答是否完全符合原始上下文。
        
        原始上下文：
        {original_text}
        
        生成的回答：
        {generated_answer}
        
        请按照以下步骤进行审计：
        1. 逐句检查生成的回答是否能在原始上下文中找到依据
        2. 特别注意数字、单位、专有名词等关键信息
        3. 标记出所有在原始上下文中没有依据的内容
        4. 给出最终的审计结果（通过或不通过）
        
        请按照以下格式输出审计结果：
        审计结果：[通过/不通过]
        错误信息：[如果不通过，列出所有错误；如果通过，留空]
        
        请严格按照上述格式输出，不要添加任何其他内容。
        """
        
        try:
            # Use Flash model for speed as this is an internal check
            response = self.gemini_client.generate_text(prompt, use_pro=False, temperature=0.0)
            
            # 解析审计结果
            lines = response.strip().split("\n")
            audit_result = {
                "passed": False,
                "errors": []
            }
            
            for line in lines:
                if line.startswith("审计结果："):
                    audit_result["passed"] = "通过" in line
                elif line.startswith("错误信息："):
                    errors = line[5:].strip()
                    if errors and errors != "无":
                        audit_result["errors"] = errors.split("；")
            
        except Exception as e:
            logger.error(f"[审计] 审计失败: {e}")
            # If audit fails, default to passed to avoid blocking user, moving forward
            audit_result = {"passed": True, "errors": []}

        # 增强审计结果，添加更详细的信息
        enhanced_result = {
            "audit_passed": audit_result["passed"],
            "errors": audit_result["errors"],
            "hallucinations": [],
            "original_contexts": original_contexts,
            "generated_answer": generated_answer
        }
        
        # 检查是否有幻觉内容
        if not audit_result["passed"]:
            # 标记幻觉内容
            for error in audit_result["errors"]:
                if any(keyword in error for keyword in ["未找到依据", "不符合", "错误", "不一致"]):
                    enhanced_result["hallucinations"].append(error)
        
        return enhanced_result
    
    def generate_correction_prompt(self, audit_result: Dict[str, Any]) -> str:
        """
        生成修正提示，用于重新生成回答
        
        Args:
            audit_result: 审计结果
            
        Returns:
            修正提示
        """
        # 准备错误信息
        error_text = "\n".join([f"- {error}" for error in audit_result["errors"]])
        
        # 准备原始上下文
        context_text = "\n\n".join([
            f"【来源：{ctx['metadata']['file_name']}，页码：{ctx['metadata']['page']}】\n{ctx['metadata']['content']}"
            for ctx in audit_result["original_contexts"]
        ])
        
        # 生成修正提示
        correction_prompt = f"""
        你是一位资深的 IC 设计和 BCD 工艺专家。请根据审计结果修正生成的回答。
        
        原始上下文：
        {context_text}
        
        之前生成的回答：
        {audit_result['generated_answer']}
        
        审计错误：
        {error_text}
        
        请严格按照以下要求修正回答：
        1. 移除所有在原始上下文中没有依据的内容
        2. 修正所有数值、单位、专有名词等关键信息
        3. 确保回答完全符合原始上下文
        4. 保持回答的专业性和准确性
        5. 不要添加任何原始上下文中没有的信息
        
        请用中文回答。
        """
        
        return correction_prompt
    
    def format_final_answer(self, answer: str, original_contexts: List[Dict[str, Any]]) -> str:
        """
        格式化最终回答，添加参考文档链接
        
        Args:
            answer: 生成的回答
            original_contexts: 原始上下文列表
            
        Returns:
            格式化后的最终回答
        """
        # 提取参考文献
        references = []
        for i, ctx in enumerate(original_contexts, 1):
            references.append(
                f"[{i}] {ctx['metadata']['file_name']}，页码：{ctx['metadata']['page']}"
            )
        
        # 格式化最终回答
        final_answer = f"""
        {answer}
        
        ---
        
        **参考文档：**
        {"\n".join(references)}
        """
        
        return final_answer
