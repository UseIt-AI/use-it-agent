"""
获取当前 AutoCAD 图纸信息
简洁版 - 一键获取所有关键信息
"""
from .controller import AutoCADController


def get_current_drawing_info():
    """获取并显示当前打开的AutoCAD图纸信息"""
    
    # 创建控制器并连接
    cad = AutoCADController()
    
    print("\n正在连接到 AutoCAD...")
    if not cad.connect():
        print("❌ 连接失败！")
        print("请确保：")
        print("  1. AutoCAD 已经打开")
        print("  2. AutoCAD 中已打开图纸")
        return None
    
    print("✅ 连接成功！\n")
    
    # ========== 收集所有信息 ==========
    
    # 1. 基本信息
    basic_info = cad.get_drawing_info()
    
    # 2. 图层信息
    layers = cad.get_layer_details()
    
    # 3. 实体统计
    entities = cad.get_entities_by_type()
    
    # 4. 边界信息
    bounds = cad.get_bounds()
    
    # 5. 图块统计
    blocks = cad.get_blocks_count()
    
    # 6. 布局和视口信息
    viewports_info = cad.get_all_viewports_info()
    
    # ========== 格式化输出 ==========
    
    print("=" * 80)
    print(" " * 25 + "📐 AutoCAD 图纸信息报告")
    print("=" * 80)
    
    # --- 基本信息 ---
    print("\n【基本信息】")
    print("-" * 80)
    print(f"  文件名称      : {basic_info.get('文件名', 'N/A')}")
    print(f"  完整路径      : {basic_info.get('完整路径', '未保存')}")
    print(f"  AutoCAD 版本  : {basic_info.get('AutoCAD版本', 'N/A')}")
    print(f"  是否已保存    : {'否' if basic_info.get('是否已保存') else '是'}")
    print(f"  是否只读      : {'是' if basic_info.get('是否只读') else '否'}")
    
    # --- 内容统计 ---
    print("\n【内容统计】")
    print("-" * 80)
    print(f"  图层总数      : {basic_info.get('图层总数', 0)} 个")
    print(f"  当前图层      : {basic_info.get('当前图层', 'N/A')}")
    print(f"  模型空间实体  : {basic_info.get('模型空间实体数', 0)} 个")
    print(f"  图纸空间实体  : {basic_info.get('图纸空间实体数', 0)} 个")
    
    # --- 实体分布 ---
    if entities:
        print("\n【实体分布】")
        print("-" * 80)
        
        # 实体类型中文名称映射
        type_names = {
            'AcDbLine': '直线',
            'AcDbCircle': '圆',
            'AcDbArc': '圆弧',
            'AcDbPolyline': '多段线',
            'AcDbLWPolyline': '轻量多段线',
            'AcDbText': '文字',
            'AcDbMText': '多行文字',
            'AcDbHatch': '填充',
            'AcDbBlockReference': '块参照',
            'AcDbDimension': '标注',
            'AcDbRotatedDimension': '旋转标注',
            'AcDbAlignedDimension': '对齐标注',
        }
        
        total_entities = sum(entities.values())
        # 显示前5种最常见的实体
        sorted_entities = sorted(entities.items(), key=lambda x: x[1], reverse=True)
        for i, (entity_type, count) in enumerate(sorted_entities[:5]):
            type_name = type_names.get(entity_type, entity_type)
            percentage = (count / total_entities * 100) if total_entities > 0 else 0
            print(f"  {type_name:<12} : {count:>6} 个  ({percentage:>5.1f}%)")
        
        if len(sorted_entities) > 5:
            other_count = sum(count for _, count in sorted_entities[5:])
            other_percentage = (other_count / total_entities * 100) if total_entities > 0 else 0
            print(f"  {'其他':<12} : {other_count:>6} 个  ({other_percentage:>5.1f}%)")
        
        print(f"  {'-' * 40}")
        print(f"  {'总计':<12} : {total_entities:>6} 个")
    
    # --- 图层状态 ---
    if layers:
        print("\n【图层状态】")
        print("-" * 80)
        on_layers = [l for l in layers if l['是否开启']]
        frozen_layers = [l for l in layers if l['是否冻结']]
        locked_layers = [l for l in layers if l['是否锁定']]
        
        print(f"  开启图层      : {len(on_layers)}/{len(layers)} 个")
        print(f"  冻结图层      : {len(frozen_layers)}/{len(layers)} 个")
        print(f"  锁定图层      : {len(locked_layers)}/{len(layers)} 个")
        
        # 显示前5个图层
        print(f"\n  主要图层:")
        for i, layer in enumerate(layers[:5]):
            status = "🟢" if layer['是否开启'] else "🔴"
            print(f"    {status} {layer['名称']:<20} (颜色: {layer['颜色']})")
        
        if len(layers) > 5:
            print(f"    ... 还有 {len(layers) - 5} 个图层")
    
    # --- 图块统计 ---
    if blocks:
        print("\n【图块统计】")
        print("-" * 80)
        total_blocks = sum(blocks.values())
        print(f"  图块类型数    : {len(blocks)} 种")
        print(f"  图块引用总数  : {total_blocks} 个")
        
        # 显示前3个最常用的图块
        sorted_blocks = sorted(blocks.items(), key=lambda x: x[1], reverse=True)
        print(f"\n  最常用图块:")
        for i, (block_name, count) in enumerate(sorted_blocks[:3]):
            print(f"    {i+1}. {block_name:<30} : {count} 次")
    
    # --- 图纸边界 ---
    if bounds != ((0, 0), (0, 0)):
        print("\n【图纸边界】")
        print("-" * 80)
        min_point, max_point = bounds
        width = max_point[0] - min_point[0]
        height = max_point[1] - min_point[1]
        area = width * height
        
        print(f"  最小点        : ({min_point[0]:.2f}, {min_point[1]:.2f})")
        print(f"  最大点        : ({max_point[0]:.2f}, {max_point[1]:.2f})")
        print(f"  图纸宽度      : {width:.2f}")
        print(f"  图纸高度      : {height:.2f}")
        print(f"  图纸面积      : {area:.2f}")
        
        # 判断图纸方向
        orientation = "横向" if width > height else "纵向" if height > width else "正方形"
        print(f"  图纸方向      : {orientation}")
    
    # --- 布局和视口分析 ---
    if viewports_info:
        print("\n【布局与视口】")
        print("-" * 80)
        total_small_drawings = sum(v['实际小图纸数'] for v in viewports_info.values())
        
        print(f"  图纸空间布局数: {len(viewports_info)} 个")
        print(f"  小图纸视口数  : {total_small_drawings} 个")
        
        if total_small_drawings > 0:
            print(f"\n  布局分布:")
            for layout_name, vp_info in viewports_info.items():
                if vp_info['实际小图纸数'] > 0:
                    print(f"    - {layout_name:<20} : {vp_info['实际小图纸数']} 个小图纸")
    
    # --- 单位信息 ---
    print("\n【单位设置】")
    print("-" * 80)
    insunits = basic_info.get('插入单位', 0)
    unit_names = {
        0: "无单位",
        1: "英寸",
        2: "英尺",
        4: "毫米",
        5: "厘米",
        6: "米",
        8: "英里",
        9: "千米",
    }
    unit_name = unit_names.get(insunits, f"单位代码 {insunits}")
    print(f"  插入单位      : {unit_name}")
    
    # --- 总结 ---
    print("\n【总结】")
    print("-" * 80)
    total_entities = sum(entities.values()) if entities else 0
    
    if total_entities == 0:
        print("  ⚠️  这是一张空白图纸")
    elif total_entities < 100:
        print("  ✅ 这是一张简单图纸")
    elif total_entities < 1000:
        print("  ✅ 这是一张中等复杂度图纸")
    else:
        print("  ⚠️  这是一张复杂图纸")
    
    if viewports_info and sum(v['实际小图纸数'] for v in viewports_info.values()) > 0:
        small_count = sum(v['实际小图纸数'] for v in viewports_info.values())
        print(f"  📋 包含 {small_count} 个小图纸视口")
    
    if blocks:
        print(f"  🧩 使用了 {len(blocks)} 种图块")
    
    print("\n" + "=" * 80)
    
    # 返回所有信息的字典（供程序化使用）
    return {
        '基本信息': basic_info,
        '图层信息': layers,
        '实体统计': entities,
        '图纸边界': bounds,
        '图块统计': blocks,
        '视口信息': viewports_info,
    }


def save_info_to_file(info_dict, output_file="图纸信息报告.txt"):
    """将图纸信息保存到文本文件"""
    import sys
    from io import StringIO
    
    # 保存原始stdout
    old_stdout = sys.stdout
    
    # 重定向到字符串
    sys.stdout = StringIO()
    
    # 重新生成信息
    get_current_drawing_info()
    
    # 获取输出内容
    output = sys.stdout.getvalue()
    
    # 恢复stdout
    sys.stdout = old_stdout
    
    # 保存到文件
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(output)
        print(f"\n✅ 报告已保存到: {output_file}")
        return True
    except Exception as e:
        print(f"\n❌ 保存失败: {e}")
        return False


if __name__ == "__main__":
    print("=" * 80)
    print(" " * 20 + "AutoCAD 图纸信息获取工具")
    print("=" * 80)
    print("\n请确保:")
    print("  1. AutoCAD 已经打开")
    print("  2. 图纸已经加载\n")
    
    input("按回车键开始获取信息...")
    
    # 获取并显示信息
    info = get_current_drawing_info()
    
    if info:
        print("\n" + "=" * 80)
        choice = input("\n是否保存报告到文件？(y/n): ").strip().lower()
        if choice == 'y':
            filename = input("输入文件名 (直接回车使用默认名称 '图纸信息报告.txt'): ").strip()
            if not filename:
                filename = "图纸信息报告.txt"
            
            # 重新获取信息并保存
            cad = AutoCADController()
            if cad.connect():
                import sys
                from io import StringIO
                
                old_stdout = sys.stdout
                sys.stdout = StringIO()
                
                get_current_drawing_info()
                
                output = sys.stdout.getvalue()
                sys.stdout = old_stdout
                
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(output)
                
                print(f"✅ 报告已保存到: {filename}")
    
    print("\n感谢使用！")

