#!/usr/bin/env python3
"""
快速模型测试脚本 - 测试少量模型以避免长时间等待
"""

import base64
import sys
import time
import psutil
import gc
from pathlib import Path

# Ensure parent directory (server/) is on path so we can import detection.py
sys.path.append(str(Path(__file__).resolve().parents[1]))

from detection import paddle_has_cat_from_bytes

# 快速测试的模型列表（选择几个代表性模型）
QUICK_TEST_MODELS = [
    "EfficientNetB0",
    "ResNet50", 
    "PPLCNet_x1_0",
    "PPHGNet_tiny"
]

def get_ground_truth(filename):
    """根据文件名确定真实标签：以'---'开头的不是猫，其他都是猫"""
    return not filename.startswith("---")

def get_memory_usage():
    """获取当前进程的内存使用量（MB）"""
    process = psutil.Process()
    return process.memory_info().rss / 1024 / 1024  # 转换为MB

def test_model_accuracy(model_name, test_images):
    """测试单个模型的准确率"""
    print(f"\n=== 测试模型: {model_name} ===")
    
    # 清理内存并记录初始内存使用
    gc.collect()
    initial_memory = get_memory_usage()
    print(f"  初始内存使用: {initial_memory:.1f} MB")
    
    correct_predictions = 0
    total_predictions = 0
    errors = 0
    start_time = time.time()
    
    for img_path, ground_truth in test_images:
        try:
            data = img_path.read_bytes()
            predicted_cat, err = paddle_has_cat_from_bytes(data, model_name)
            
            if err:
                print(f"  {img_path.name} -> ERROR: {err}")
                errors += 1
                continue
                
            is_correct = (predicted_cat == ground_truth)
            if is_correct:
                correct_predictions += 1
                print(f"  {img_path.name} -> 预测: {predicted_cat}, 实际: {ground_truth} ✅")
            else:
                print(f"  {img_path.name} -> 预测: {predicted_cat}, 实际: {ground_truth} ❌")
            
            total_predictions += 1
            
        except Exception as e:
            print(f"  {img_path.name} -> EXCEPTION: {e}")
            errors += 1
    
    end_time = time.time()
    inference_time = end_time - start_time
    
    # 记录最终内存使用
    final_memory = get_memory_usage()
    memory_used = final_memory - initial_memory
    
    if total_predictions > 0:
        accuracy = correct_predictions / total_predictions
        avg_time = inference_time / total_predictions
        print(f"  准确率: {accuracy:.2%} ({correct_predictions}/{total_predictions})")
        print(f"  平均推理时间: {avg_time:.3f}秒")
        print(f"  总推理时间: {inference_time:.3f}秒")
        print(f"  内存使用: {memory_used:.1f} MB (从 {initial_memory:.1f} MB 到 {final_memory:.1f} MB)")
        print(f"  错误数: {errors}")
        return {
            'model': model_name,
            'accuracy': accuracy,
            'correct': correct_predictions,
            'total': total_predictions,
            'errors': errors,
            'avg_time': avg_time,
            'total_time': inference_time,
            'memory_used': memory_used,
            'initial_memory': initial_memory,
            'final_memory': final_memory
        }
    else:
        print(f"  无法测试模型 {model_name}")
        return None

if __name__ == "__main__":
    test_dir = Path(__file__).parent
    jpg_files = sorted(test_dir.glob("*.jpg"))

    if not jpg_files:
        print("No .jpg files found in", test_dir)
        raise SystemExit(1)

    print(f"找到 {len(jpg_files)} 个测试图片")
    
    # 准备测试数据
    test_images = []
    for img_path in jpg_files:
        ground_truth = get_ground_truth(img_path.name)
        test_images.append((img_path, ground_truth))
        print(f"  {img_path.name} -> {'猫' if ground_truth else '非猫'}")
    
    # 测试模型
    results = []
    for model_name in QUICK_TEST_MODELS:
        try:
            print(f"\n正在加载模型 {model_name}...")
            result = test_model_accuracy(model_name, test_images)
            if result:
                results.append(result)
            # 清理内存，为下一个模型做准备
            gc.collect()
        except Exception as e:
            print(f"模型 {model_name} 测试失败: {e}")
            gc.collect()
    
    # 打印结果汇总
    if results:
        print(f"\n{'='*80}")
        print("模型性能汇总:")
        print(f"{'='*80}")
        print(f"{'模型名称':<20} {'准确率':<10} {'正确/总数':<12} {'平均时间':<10} {'内存使用':<10}")
        print(f"{'-'*80}")
        
        # 按准确率排序
        results.sort(key=lambda x: x['accuracy'], reverse=True)
        
        for result in results:
            print(f"{result['model']:<20} {result['accuracy']:<10.2%} {result['correct']}/{result['total']:<8} {result['avg_time']:<10.3f}s {result['memory_used']:<10.1f}MB")
        
        # 找出最佳模型
        best_model = results[0]
        print(f"\n🏆 最佳模型: {best_model['model']}")
        print(f"   准确率: {best_model['accuracy']:.2%}")
        print(f"   平均推理时间: {best_model['avg_time']:.3f}秒")
        print(f"   内存使用: {best_model['memory_used']:.1f} MB")
        
        # 内存使用分析
        print(f"\n📊 内存使用分析:")
        memory_results = sorted(results, key=lambda x: x['memory_used'])
        print(f"   最省内存: {memory_results[0]['model']} ({memory_results[0]['memory_used']:.1f} MB)")
        print(f"   最耗内存: {memory_results[-1]['model']} ({memory_results[-1]['memory_used']:.1f} MB)")
        
        # 效率分析（准确率/内存使用）
        print(f"\n⚡ 效率分析 (准确率/内存使用):")
        efficiency_results = []
        for result in results:
            if result['memory_used'] > 0:
                efficiency = result['accuracy'] / result['memory_used']
                efficiency_results.append((result['model'], efficiency))
        
        if efficiency_results:
            efficiency_results.sort(key=lambda x: x[1], reverse=True)
            print(f"   最高效率: {efficiency_results[0][0]} ({efficiency_results[0][1]:.4f})")
            print(f"   最低效率: {efficiency_results[-1][0]} ({efficiency_results[-1][1]:.4f})")
    else:
        print("没有成功测试任何模型")
