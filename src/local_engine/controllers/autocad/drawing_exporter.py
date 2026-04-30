"""
完整版导出工具
支持标注（Dimension）对象
"""
from .controller import AutoCADController
import json
import math


def export_complete_drawing():
    """导出图纸元素，包含标注对象"""
    
    # 连接到 AutoCAD
    cad = AutoCADController()
    print("\n正在连接到 AutoCAD...")
    if not cad.connect():
        print("❌ 连接失败！请确保 AutoCAD 已打开并加载了图纸")
        return None
    
    print("✅ 连接成功！\n")
    
    # 1. 导出图层颜色信息
    print("=" * 70)
    print("【第1步】获取图层颜色信息")
    print("=" * 70)
    
    layer_colors = {}
    for layer in cad.doc.Layers:
        layer_name = layer.Name
        layer_color = layer.Color
        layer_colors[layer_name] = layer_color
        print(f"  图层 '{layer_name}': 颜色 {layer_color}")
    
    print(f"\n✅ 共 {len(layer_colors)} 个图层\n")
    
    # 2. 导出元素
    print("=" * 70)
    print("【第2步】导出图形元素（包括标注）")
    print("=" * 70)
    
    elements = {
        'lines': [],
        'circles': [],
        'arcs': [],
        'polylines': [],
        'texts': [],
        'dimensions': [],  # 新增：标注
    }
    
    total = cad.model_space.Count
    print(f"开始扫描图纸，共 {total} 个实体...\n")
    
    count = 0
    dim_count = 0
    
    # 遍历所有实体
    for entity in cad.model_space:
        try:
            entity_type = entity.ObjectName
            
            # 直线
            if entity_type == 'AcDbLine':
                start = entity.StartPoint
                end = entity.EndPoint
                elements['lines'].append({
                    'start': [start[0], start[1], start[2]],
                    'end': [end[0], end[1], end[2]],
                    'layer': entity.Layer,
                    'color': entity.Color,
                })
                count += 1
            
            # 圆
            elif entity_type == 'AcDbCircle':
                center = entity.Center
                elements['circles'].append({
                    'center': [center[0], center[1], center[2]],
                    'radius': entity.Radius,
                    'layer': entity.Layer,
                    'color': entity.Color,
                })
                count += 1
            
            # 圆弧
            elif entity_type == 'AcDbArc':
                center = entity.Center
                elements['arcs'].append({
                    'center': [center[0], center[1], center[2]],
                    'radius': entity.Radius,
                    'start_angle': math.degrees(entity.StartAngle),
                    'end_angle': math.degrees(entity.EndAngle),
                    'layer': entity.Layer,
                    'color': entity.Color,
                })
                count += 1
            
            # 多段线
            elif entity_type in ['AcDbPolyline', 'AcDbLWPolyline']:
                coords = entity.Coordinates
                vertices = []
                for i in range(0, len(coords), 2):
                    vertices.append([coords[i], coords[i+1]])
                
                elements['polylines'].append({
                    'vertices': vertices,
                    'closed': entity.Closed if hasattr(entity, 'Closed') else False,
                    'layer': entity.Layer,
                    'color': entity.Color,
                })
                count += 1
            
            # 文字
            elif entity_type == 'AcDbText':
                pos = entity.InsertionPoint
                elements['texts'].append({
                    'text': entity.TextString,
                    'position': [pos[0], pos[1], pos[2]],
                    'height': entity.Height,
                    'layer': entity.Layer,
                    'color': entity.Color,
                })
                count += 1
            
            # 标注对象 - 各种类型
            elif 'Dimension' in entity_type:
                dim_count += 1
                try:
                    dim_data = extract_dimension(entity, entity_type)
                    if dim_data:
                        elements['dimensions'].append(dim_data)
                        count += 1
                        
                        if dim_count <= 3:
                            print(f"  发现标注 {dim_count}: {entity_type}")
                            print(f"    测量值: {dim_data.get('measurement', 'N/A')}")
                except Exception as e:
                    print(f"  ⚠️ 标注 {dim_count} 提取失败: {e}")
            
            # 进度显示
            if count % 100 == 0 and count > 0:
                print(f"  已处理 {count} 个元素...")
                
        except Exception as e:
            continue
    
    # 打印统计
    print()
    print("=" * 70)
    print("导出完成！")
    print("=" * 70)
    print(f"直线        : {len(elements['lines'])} 条")
    print(f"圆          : {len(elements['circles'])} 个")
    print(f"圆弧        : {len(elements['arcs'])} 个")
    print(f"多段线      : {len(elements['polylines'])} 条")
    print(f"文字        : {len(elements['texts'])} 个")
    print(f"标注        : {len(elements['dimensions'])} 个  ⭐ 新增")
    print("-" * 70)
    print(f"总计        : {count} 个")
    print("=" * 70)
    
    if len(elements['dimensions']) > 0:
        print(f"\n✅ 成功导出 {len(elements['dimensions'])} 个标注对象！")
    else:
        print(f"\n⚠️  未发现标注对象")
    
    # 3. 组合数据
    result = {
        'layer_colors': layer_colors,
        'elements': elements
    }
    
    return result


def extract_dimension(entity, entity_type):
    """提取标注对象的信息"""
    try:
        dim_data = {
            'type': entity_type,
            'layer': entity.Layer,
            'color': entity.Color,
        }
        
        # 获取标注的测量值
        if hasattr(entity, 'Measurement'):
            dim_data['measurement'] = entity.Measurement
        
        # 获取标注文字覆盖
        if hasattr(entity, 'TextOverride'):
            dim_data['text_override'] = entity.TextOverride
        
        # 获取标注文字位置
        if hasattr(entity, 'TextPosition'):
            pos = entity.TextPosition
            dim_data['text_position'] = [pos[0], pos[1], pos[2]]
        
        # 获取标注旋转角度
        if hasattr(entity, 'Rotation'):
            dim_data['rotation'] = math.degrees(entity.Rotation)
        
        # 根据不同类型获取特定属性
        
        # 对齐标注 (Aligned Dimension)
        if entity_type == 'AcDbAlignedDimension':
            if hasattr(entity, 'ExtLine1Point'):
                pt = entity.ExtLine1Point
                dim_data['ext_line1_point'] = [pt[0], pt[1], pt[2]]
            if hasattr(entity, 'ExtLine2Point'):
                pt = entity.ExtLine2Point
                dim_data['ext_line2_point'] = [pt[0], pt[1], pt[2]]
            if hasattr(entity, 'DimLinePoint'):
                pt = entity.DimLinePoint
                dim_data['dim_line_point'] = [pt[0], pt[1], pt[2]]
        
        # 旋转标注 (Rotated Dimension)
        elif entity_type == 'AcDbRotatedDimension':
            if hasattr(entity, 'ExtLine1Point'):
                pt = entity.ExtLine1Point
                dim_data['ext_line1_point'] = [pt[0], pt[1], pt[2]]
            if hasattr(entity, 'ExtLine2Point'):
                pt = entity.ExtLine2Point
                dim_data['ext_line2_point'] = [pt[0], pt[1], pt[2]]
            if hasattr(entity, 'DimLinePoint'):
                pt = entity.DimLinePoint
                dim_data['dim_line_point'] = [pt[0], pt[1], pt[2]]
            if hasattr(entity, 'Rotation'):
                dim_data['dim_rotation'] = math.degrees(entity.Rotation)
        
        # 半径标注 (Radial Dimension)
        elif entity_type == 'AcDbRadialDimension':
            if hasattr(entity, 'Center'):
                pt = entity.Center
                dim_data['center'] = [pt[0], pt[1], pt[2]]
            if hasattr(entity, 'ChordPoint'):
                pt = entity.ChordPoint
                dim_data['chord_point'] = [pt[0], pt[1], pt[2]]
        
        # 直径标注 (Diametric Dimension)
        elif entity_type == 'AcDbDiametricDimension':
            if hasattr(entity, 'ChordPoint'):
                pt = entity.ChordPoint
                dim_data['chord_point'] = [pt[0], pt[1], pt[2]]
            if hasattr(entity, 'FarChordPoint'):
                pt = entity.FarChordPoint
                dim_data['far_chord_point'] = [pt[0], pt[1], pt[2]]
        
        # 角度标注 (Angular Dimension)
        elif entity_type in ['AcDbAngularDimension', 'AcDb3PointAngularDimension']:
            if hasattr(entity, 'ArcPoint'):
                pt = entity.ArcPoint
                dim_data['arc_point'] = [pt[0], pt[1], pt[2]]
        
        return dim_data
        
    except Exception as e:
        print(f"    提取标注信息失败: {e}")
        return None


def save_complete_data(data, filename='drawing_with_dimensions.json'):
    """保存完整数据"""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"\n✅ 完整数据已保存到: {filename}")
        
        # 同时保存一个可读的摘要
        summary_file = filename.replace('.json', '_summary.txt')
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write("=" * 70 + "\n")
            f.write("图纸导出摘要\n")
            f.write("=" * 70 + "\n\n")
            
            f.write("图层颜色:\n")
            for layer, color in data['layer_colors'].items():
                f.write(f"  {layer}: {color}\n")
            
            f.write("\n元素统计:\n")
            elements = data['elements']
            f.write(f"  直线: {len(elements.get('lines', []))}\n")
            f.write(f"  圆: {len(elements.get('circles', []))}\n")
            f.write(f"  圆弧: {len(elements.get('arcs', []))}\n")
            f.write(f"  多段线: {len(elements.get('polylines', []))}\n")
            f.write(f"  文字: {len(elements.get('texts', []))}\n")
            f.write(f"  标注: {len(elements.get('dimensions', []))}\n")
            
            if elements.get('dimensions'):
                f.write("\n标注详情:\n")
                for i, dim in enumerate(elements['dimensions'][:10], 1):
                    f.write(f"  {i}. 类型: {dim['type']}, ")
                    f.write(f"图层: {dim['layer']}, ")
                    f.write(f"测量值: {dim.get('measurement', 'N/A')}\n")
                
                if len(elements['dimensions']) > 10:
                    f.write(f"  ... 还有 {len(elements['dimensions']) - 10} 个标注\n")
        
        print(f"✅ 摘要已保存到: {summary_file}")
        return True
    except Exception as e:
        print(f"\n❌ 保存失败: {e}")
        return False


def main():
    """主程序"""
    print("=" * 70)
    print(" " * 15 + "完整版图纸导出工具")
    print(" " * 18 + "(支持标注对象)")
    print("=" * 70)
    print()
    print("功能：")
    print("  ✅ 导出所有图形元素")
    print("  ✅ 导出图层颜色信息")
    print("  ✅ 导出标注对象 ⭐ 新增")
    print("  ✅ 生成复刻代码")
    print()
    print("请确保 AutoCAD 已打开并加载了要导出的图纸")
    print("=" * 70)
    print()
    
    input("按回车键开始...")
    
    # 导出数据
    data = export_complete_drawing()
    
    if not data:
        return
    
    # 保存数据
    print()
    save_complete_data(data, 'drawing_with_dimensions.json')
    
    print()
    print("=" * 70)
    print("✅ 导出完成！")
    print("=" * 70)
    print()
    print("生成的文件：")
    print("  📄 drawing_with_dimensions.json - 完整数据")
    print("  📄 drawing_with_dimensions_summary.txt - 可读摘要")
    print()
    print("下一步：")
    print("  运行复刻工具来重建图纸（包括标注）")
    print()


if __name__ == "__main__":
    main()

