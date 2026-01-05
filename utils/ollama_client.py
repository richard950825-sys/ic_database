from ollama import Client as OllamaAPIClient
from dotenv import load_dotenv
import os
import logging

logger = logging.getLogger(__name__)

# 加载环境变量
load_dotenv()

# 设置全局代理
http_proxy = os.getenv("HTTP_PROXY")
https_proxy = os.getenv("HTTPS_PROXY")
if http_proxy:
    os.environ["HTTP_PROXY"] = http_proxy
    os.environ["http_proxy"] = http_proxy
if https_proxy:
    os.environ["HTTPS_PROXY"] = https_proxy
    os.environ["https_proxy"] = https_proxy
    
logger.info(f"[OllamaClient] 环境代理设置 - HTTP: {http_proxy}, HTTPS: {https_proxy}")

class OllamaClient:
    def __init__(self):
        """
        初始化 Ollama 客户端
        """
        self.client = OllamaAPIClient(host=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
        self.default_model = "llama3.1"
        self.ollama_available = self._test_connection()
        self.gemini_client = None
        
        # 如果启动时检测到 Ollama 不可用，立即尝试初始化 Gemini
        if not self.ollama_available:
            logger.warning("[OllamaClient] Ollama 连接失败，将在首次请求时使用 Gemini 作为回退方案")
    
    def _test_connection(self) -> bool:
        """
        测试 Ollama 连接是否可用
        
        Returns:
            连接是否可用
        """
        try:
            logger.info("[OllamaClient] 测试 Ollama 连接...")
            self.client.list()
            logger.info("[OllamaClient] Ollama 连接成功")
            return True
        except Exception as e:
            logger.error(f"[OllamaClient] Ollama 连接失败: {str(e)}")
            return False
    
    def generate_text(self, prompt: str, model: str = None, temperature: float = 0.1) -> str:
        """
        生成文本内容
        
        Args:
            prompt: 提示词
            model: 使用的模型（默认使用 llama3.1）
            temperature: 生成温度
            
        Returns:
            生成的文本
        """
        # 如果 Ollama 可用，使用 Ollama
        if self.ollama_available:
            try:
                model = model or self.default_model
                response = self.client.generate(model=model, prompt=prompt, options={"temperature": temperature})
                return response["response"]
            except Exception as e:
                logger.error(f"[OllamaClient] Ollama 生成文本失败: {str(e)}，尝试使用 Gemini 回退")
                self.ollama_available = False
        
        # 如果 Ollama 不可用，使用 Gemini 回退
        if not self.ollama_available:
            # Lazy load Gemini client if not already initialized
            if not self.gemini_client:
                try:
                    from utils.gemini_client import GeminiClient
                    self.gemini_client = GeminiClient()
                    logger.info("[OllamaClient] 运行时初始化 Gemini 回退方案成功")
                except Exception as e:
                    logger.error(f"[OllamaClient] 无法初始化 Gemini 回退方案: {str(e)}")

        if self.gemini_client:
            try:
                logger.debug("[OllamaClient] 使用 Gemini 生成文本")
                result = self.gemini_client.generate_text(prompt, use_pro=True)
                if result:
                    return result
                else:
                    logger.warning("[OllamaClient] Gemini 返回空内容")
            except Exception as e:
                logger.error(f"[OllamaClient] Gemini 生成文本失败: {str(e)}")
        
        # 如果都失败了，返回错误信息
        # 为了防止崩溃，这里返回一个默认的失败消息而不是抛出异常
        logger.error("无法生成文本：Ollama 和 Gemini 都不可用")
        return "审计无法完成：模型服务不可用"
    
    def audit_response(self, original_context: str, generated_answer: str) -> dict:
        """
        审计生成的回答是否符合原始上下文
        
        Args:
            original_context: 原始上下文
            generated_answer: 生成的回答
            
        Returns:
            审计结果，包含是否通过、错误信息等
        """
        prompt = f"""
        你是一位严格的事实审计专家，负责检查生成的回答是否完全符合原始上下文。
        
        原始上下文：
        {original_context}
        
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
        
        response = self.generate_text(prompt, temperature=0.0)
        
        # 解析审计结果
        lines = response.strip().split("\n")
        result = {
            "passed": False,
            "errors": []
        }
        
        for line in lines:
            if line.startswith("审计结果："):
                result["passed"] = "通过" in line
            elif line.startswith("错误信息："):
                errors = line[5:].strip()
                if errors:
                    result["errors"] = errors.split("；")
        
        return result
    
    def route_query(self, query: str) -> str:
        """
        将用户查询路由到不同的处理流程
        
        Args:
            query: 用户查询
            
        Returns:
            路由结果，可能的值：
            - FACTUAL: 事实查询，需要精确匹配
            - CONCEPTUAL: 概念查询，需要语义检索
            - RELATIONAL: 关系查询，需要图谱探索
            - COMPARATIVE: 比较查询，需要表格对比
        """
        try:
            prompt = f"""
            你是一位路由专家，负责将用户的 IC 设计和 BCD 工艺相关查询分类到正确的处理流程。
            
            请根据以下规则进行分类：
            1. 如果是询问具体工艺参数（数字、单位），必须路由到 'FACTUAL'
            2. 如果是询问跨模块影响或实体关系，路由到 'RELATIONAL'
            3. 如果是询问概念解释或原理，路由到 'CONCEPTUAL'
            4. 如果是询问比较或对比，路由到 'COMPARATIVE'
            
            用户查询：{query}
            
            请只输出路由结果，不要添加任何其他解释。
            """
            
            response = self.generate_text(prompt, temperature=0.0)
            return response.strip()
        except Exception as e:
            logger.error(f"[OllamaClient] 路由查询失败: {str(e)}，使用默认路由 CONCEPTUAL")
            return "CONCEPTUAL"
