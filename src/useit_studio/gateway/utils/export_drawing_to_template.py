import os
import sys

# 将项目根目录添加到 python path，以便导入 autocad_controller
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)

from autocad_controller.autocad_controller import AutoCADController

def export_current_drawing():
    cad = AutoCADController()
    
    print("正在连接 AutoCAD...")
    if not cad.connect():
        print("❌ 未找到运行中的 AutoCAD 实例，请先打开图纸。")
        return

    # 定义输出目录: drawing/u_channel_template/cut_and_fill_canal
    output_dir = os.path.join(project_root, "drawing", "u_channel_template", "cut_and_fill_canal")
    
    # 如果目录不存在则创建
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"创建目录: {output_dir}")

    # 定义输出文件名
    # 注意：这里我们将所有内容提取到一个文件中。
    # 现有的 excavated_canal 是拆分成多个文件的 (1_xxx, 2_xxx...)
    # 提取后您可以手动拆分，或者直接作为一个整体模板使用。
    output_file = os.path.join(output_dir, "base_template.json")

    print(f"正在提取图纸数据并保存到: {output_file}")
    cad.save_as_template(output_file)
    print("[OK] 导出完成！")

if __name__ == "__main__":
    export_current_drawing()

