import os
import sys
from math import ceil

# 尝试导入 pypdf，如果不存在则提示安装
try:
    from pypdf import PdfReader, PdfWriter
except ImportError:
    print("错误: 未找到 'pypdf' 库。")
    print("请运行以下命令进行安装: pip install pypdf")
    sys.exit(1)

def split_pdf(file_path, chunk_size=30):
    """
    将 PDF 文件按指定页数切分
    :param file_path: PDF 文件路径
    :param chunk_size: 每个分片的页数 (默认 30)
    """
    # 路径清理（去除引号）
    file_path = file_path.strip('"').strip("'")

    if not os.path.exists(file_path):
        print(f"错误: 文件 '{file_path}' 不存在。")
        return

    try:
        reader = PdfReader(file_path)
        total_pages = len(reader.pages)
        
        if total_pages == 0:
            print("错误: PDF 文件为空。")
            return

        base_name = os.path.splitext(file_path)[0]
        ext = os.path.splitext(file_path)[1]
        num_chunks = ceil(total_pages / chunk_size)
        
        print(f"文档信息: {os.path.basename(file_path)}")
        print(f"总页数: {total_pages}")
        print(f"计划切分为 {num_chunks} 份 (每份 {chunk_size} 页)...")
        print("-" * 30)

        for i in range(0, total_pages, chunk_size):
            writer = PdfWriter()
            start_page = i
            end_page = min(i + chunk_size, total_pages)
            
            # 由于 pypdf 的 lazy loading 特性，这里直接添加页引用
            for page_num in range(start_page, end_page):
                writer.add_page(reader.pages[page_num])
            
            chunk_index = (i // chunk_size) + 1
            output_filename = f"{base_name}_part{chunk_index}{ext}"
            
            with open(output_filename, "wb") as out_file:
                writer.write(out_file)
            
            print(f"[✓] 已保存: {os.path.basename(output_filename)} (页码 {start_page+1}-{end_page})")
            
        print("-" * 30)
        print("切分完成！")

    except Exception as e:
        print(f"发生错误: {e}")

def process_path(raw_input):
    # 清洗逻辑
    clean_path = raw_input.strip()
    
    # 移除 PowerShell 的调用符 '& ' (如果拖入导致)
    if clean_path.startswith("& "):
        clean_path = clean_path[2:].strip()
        
    # 移除首尾引号
    clean_path = clean_path.strip('"').strip("'")
    
    print(f"🔍 检测路径: {clean_path}") # Removed brackets to avoid confusion
    print(f"   (Raw): {repr(clean_path)}")
    
    if os.path.exists(clean_path):
        if os.path.isdir(clean_path):
            print(f"⚠️  这是一个文件夹。正在查找内部的 PDF 文件...")
            files = [f for f in os.listdir(clean_path) if f.lower().endswith('.pdf')]
            if not files:
                print("❌ 该文件夹内没有找到 .pdf 文件")
                return
            
            print(f"✓ 找到 {len(files)} 个 PDF 文件:")
            for f in files:
                full_p = os.path.join(clean_path, f)
                print(f"   - {f}")
                split_pdf(full_p, chunk_size=30)
        else:
            split_pdf(clean_path, chunk_size=30)
    else:
        print(f"❌ 错误: 文件不存在 (os.path.exists returned False)")
        print(f"   请检查路径是否正确，或者是否有权限访问。")

if __name__ == "__main__":
    print("=== PDF 切分工具 (30页/份) ===")
    print("提示: 您可以直接将文件拖入此窗口")
    
    if len(sys.argv) > 1:
        # 命令行模式
        raw_input = sys.argv[1]
        process_path(raw_input)
    else:
        # 交互模式 Loop
        while True:
            try:
                raw_input = input("\n[拖入文件] 请输入 PDF 文件路径 (或输入 q 退出): ")
                if not raw_input: continue
                if raw_input.lower() in ['q', 'quit', 'exit']:
                    break
                
                process_path(raw_input)
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"❌ 输入错误: {e}")

