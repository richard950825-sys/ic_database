from utils.ollama_client import OllamaClient
from typing import List, Dict, Any

class ResponseAuditor:
    def __init__(self):
        """
        初始化响应审计器
        """
        self.ollama_client = OllamaClient()
    
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
        
        # 使用 Ollama 进行审计
        audit_result = self.ollama_client.audit_response(original_text, generated_answer)
        
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
