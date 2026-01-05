import io
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
import matplotlib.pyplot as plt
import numpy as np

def create_bcd_test_pdf(filename="BCD_Process_RAG_Test.pdf"):
    doc = SimpleDocTemplate(filename, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []

    # --- 1. 标题 ---
    title_style = styles['Title']
    story.append(Paragraph("Advanced BCD Technology for Analog IC Design", title_style))
    story.append(Spacer(1, 0.2 * inch))

    # --- 2. 文本段落 (测试文本语义理解) ---
    # 内容涉及 BCD 工艺定义和模拟 IC 设计挑战
    text_content = """
    <b>1. Introduction to BCD Process</b><br/>
    The BCD (Bipolar-CMOS-DMOS) process technology is a cornerstone of modern power management IC (PMIC) design.
    It integrates three distinct distinct device types onto a single die:
    <b>Bipolar</b> transistors for precise analog functions (bandgaps, sensors),
    <b>CMOS</b> for digital logic and control, and
    <b>DMOS</b> (Double-Diffused MOS) for high-voltage power switching.
    A key challenge in 180nm BCD generation is the trade-off between the Specific On-Resistance (R_on,sp) and the Breakdown Voltage (BV_dss).
    Designers must utilize Shallow Trench Isolation (STI) to minimize latch-up risks in high-noise environments.
    """
    normal_style = styles['BodyText']
    story.append(Paragraph(text_content, normal_style))
    story.append(Spacer(1, 0.2 * inch))

    # --- 3. 公式生成 (测试图片/公式识别) ---
    # 使用 Matplotlib 将 LaTeX 公式渲染为图片插入，测试 RAG 是否能识别图片中的数学含义
    story.append(Paragraph("<b>2. Key Figure of Merit (FOM)</b>", styles['Heading2']))
    story.append(Paragraph("The efficiency of the LDMOS device is often evaluated using the Baliga Figure of Merit (BFOM), defined as:", normal_style))
    
    def generate_formula_image():
        fig = plt.figure(figsize=(4, 1))
        # 渲染复杂公式
        plt.text(0.5, 0.5, r"$BFOM = \frac{V_{BR}^2}{R_{on,sp}}$", fontsize=20, ha='center', va='center')
        plt.axis('off')
        img_buf = io.BytesIO()
        plt.savefig(img_buf, format='png', bbox_inches='tight', dpi=300)
        img_buf.seek(0)
        return img_buf

    formula_img = Image(generate_formula_image(), width=2*inch, height=0.5*inch)
    story.append(formula_img)
    story.append(Paragraph("Where V_BR is the breakdown voltage and R_on,sp is the specific on-resistance.", normal_style))
    story.append(Spacer(1, 0.2 * inch))

    # --- 4. 复杂表格 (测试表格结构提取) ---
    # 模拟不同工艺节点的参数对比
    story.append(Paragraph("<b>3. Process Node Comparison</b>", styles['Heading2']))
    
    data = [
        ['Parameter', '0.35um BCD', '0.18um BCD', '0.11um BCD'],
        ['Gate Oxide Thickness (A)', '70 / 250', '35 / 120', '28 / 60'],
        ['Max Logic Density (kGates/mm2)', '15', '85', '220'],
        ['Power Device (LDMOS) BV', '12V - 60V', '5V - 100V', '5V - 80V'],
        ['Mask Layers (Typical)', '18', '24', '32']
    ]
    
    t = Table(data)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(t)
    story.append(Spacer(1, 0.2 * inch))

    # --- 5. 图表生成 (测试视觉图表分析) ---
    # 绘制 LDMOS 的 IV 曲线
    story.append(Paragraph("<b>4. LDMOS Output Characteristics</b>", styles['Heading2']))
    story.append(Paragraph("The following chart illustrates the saturation behavior of the n-type LDMOS at different Gate voltages (Vgs).", normal_style))

    def generate_chart_image():
        fig, ax = plt.subplots(figsize=(5, 3))
        vds = np.linspace(0, 10, 100)
        
        # 模拟 IV 曲线
        for vgs in [3, 4, 5]:
            # 简单的 MOSFET 饱和公式模拟
            k = 0.5 * (vgs - 1)  # 简化的增益
            id_sat = []
            for v in vds:
                if v < (vgs - 1):
                    current = k * (2*(vgs-1)*v - v**2) # 线性区
                else:
                    current = k * (vgs-1)**2 # 饱和区
                id_sat.append(current)
            ax.plot(vds, id_sat, label=f'Vgs = {vgs}V')

        ax.set_title('Id vs Vds (nLDMOS)')
        ax.set_xlabel('Vds (V)')
        ax.set_ylabel('Drain Current (mA)')
        ax.legend()
        ax.grid(True)
        
        img_buf = io.BytesIO()
        plt.savefig(img_buf, format='png', dpi=300)
        img_buf.seek(0)
        return img_buf

    chart_img = Image(generate_chart_image(), width=5*inch, height=3*inch)
    story.append(chart_img)

    # 生成 PDF
    doc.build(story)
    print(f"PDF generated successfully: {filename}")

if __name__ == "__main__":
    create_bcd_test_pdf()