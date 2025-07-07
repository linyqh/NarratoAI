#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
LLM服务测试脚本

测试新的LLM服务架构是否正常工作
"""

import asyncio
import sys
import os
from pathlib import Path
from loguru import logger

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from app.services.llm.config_validator import LLMConfigValidator
from app.services.llm.unified_service import UnifiedLLMService
from app.services.llm.exceptions import LLMServiceError


async def test_text_generation():
    """测试文本生成功能"""
    print("\n🔤 测试文本生成功能...")
    
    try:
        # 简单的文本生成测试
        prompt = "请用一句话介绍人工智能。"
        
        result = await UnifiedLLMService.generate_text(
            prompt=prompt,
            system_prompt="你是一个专业的AI助手。",
            temperature=0.7
        )
        
        print(f"✅ 文本生成成功:")
        print(f"   提示词: {prompt}")
        print(f"   生成结果: {result[:100]}...")
        
        return True
        
    except Exception as e:
        print(f"❌ 文本生成失败: {str(e)}")
        return False


async def test_json_generation():
    """测试JSON格式生成功能"""
    print("\n📄 测试JSON格式生成功能...")
    
    try:
        prompt = """
请生成一个简单的解说文案示例，包含以下字段：
- title: 标题
- content: 内容
- duration: 时长（秒）

输出JSON格式。
"""
        
        result = await UnifiedLLMService.generate_text(
            prompt=prompt,
            system_prompt="你是一个专业的文案撰写专家。",
            temperature=0.7,
            response_format="json"
        )
        
        # 尝试解析JSON
        import json
        parsed_result = json.loads(result)
        
        print(f"✅ JSON生成成功:")
        print(f"   生成结果: {json.dumps(parsed_result, ensure_ascii=False, indent=2)}")
        
        return True
        
    except json.JSONDecodeError as e:
        print(f"❌ JSON解析失败: {str(e)}")
        print(f"   原始结果: {result}")
        return False
    except Exception as e:
        print(f"❌ JSON生成失败: {str(e)}")
        return False


async def test_narration_script_generation():
    """测试解说文案生成功能"""
    print("\n🎬 测试解说文案生成功能...")
    
    try:
        prompt = """
根据以下视频描述生成解说文案：

视频内容：一个人在森林中建造木屋，首先挖掘地基，然后搭建墙壁，最后安装屋顶。

请生成JSON格式的解说文案，包含items数组，每个item包含：
- _id: 序号
- timestamp: 时间戳（格式：HH:MM:SS,mmm-HH:MM:SS,mmm）
- picture: 画面描述
- narration: 解说文案
"""
        
        result = await UnifiedLLMService.generate_narration_script(
            prompt=prompt,
            temperature=0.8,
            validate_output=True
        )
        
        print(f"✅ 解说文案生成成功:")
        print(f"   生成了 {len(result)} 个片段")
        for item in result[:2]:  # 只显示前2个
            print(f"   - {item.get('timestamp', 'N/A')}: {item.get('narration', 'N/A')[:50]}...")
        
        return True
        
    except Exception as e:
        print(f"❌ 解说文案生成失败: {str(e)}")
        return False


async def test_subtitle_analysis():
    """测试字幕分析功能"""
    print("\n📝 测试字幕分析功能...")
    
    try:
        subtitle_content = """
1
00:00:01,000 --> 00:00:05,000
大家好，欢迎来到我的频道。

2
00:00:05,000 --> 00:00:10,000
今天我们要学习如何使用人工智能。

3
00:00:10,000 --> 00:00:15,000
人工智能是一项非常有趣的技术。
"""
        
        result = await UnifiedLLMService.analyze_subtitle(
            subtitle_content=subtitle_content,
            temperature=0.7,
            validate_output=True
        )
        
        print(f"✅ 字幕分析成功:")
        print(f"   分析结果: {result[:100]}...")
        
        return True
        
    except Exception as e:
        print(f"❌ 字幕分析失败: {str(e)}")
        return False


def test_config_validation():
    """测试配置验证功能"""
    print("\n⚙️  测试配置验证功能...")
    
    try:
        # 验证所有配置
        validation_results = LLMConfigValidator.validate_all_configs()
        
        summary = validation_results["summary"]
        print(f"✅ 配置验证完成:")
        print(f"   视觉模型提供商: {summary['valid_vision_providers']}/{summary['total_vision_providers']} 有效")
        print(f"   文本模型提供商: {summary['valid_text_providers']}/{summary['total_text_providers']} 有效")
        
        if summary["errors"]:
            print(f"   发现 {len(summary['errors'])} 个错误")
            for error in summary["errors"][:3]:  # 只显示前3个错误
                print(f"     - {error}")
        
        return summary['valid_text_providers'] > 0
        
    except Exception as e:
        print(f"❌ 配置验证失败: {str(e)}")
        return False


def test_provider_info():
    """测试提供商信息获取"""
    print("\n📋 测试提供商信息获取...")
    
    try:
        provider_info = UnifiedLLMService.get_provider_info()
        
        vision_providers = list(provider_info["vision_providers"].keys())
        text_providers = list(provider_info["text_providers"].keys())
        
        print(f"✅ 提供商信息获取成功:")
        print(f"   视觉模型提供商: {', '.join(vision_providers)}")
        print(f"   文本模型提供商: {', '.join(text_providers)}")
        
        return True
        
    except Exception as e:
        print(f"❌ 提供商信息获取失败: {str(e)}")
        return False


async def run_all_tests():
    """运行所有测试"""
    print("🚀 开始LLM服务测试...")
    print("="*60)
    
    # 测试结果统计
    test_results = []
    
    # 1. 测试配置验证
    test_results.append(("配置验证", test_config_validation()))
    
    # 2. 测试提供商信息
    test_results.append(("提供商信息", test_provider_info()))
    
    # 3. 测试文本生成
    test_results.append(("文本生成", await test_text_generation()))
    
    # 4. 测试JSON生成
    test_results.append(("JSON生成", await test_json_generation()))
    
    # 5. 测试字幕分析
    test_results.append(("字幕分析", await test_subtitle_analysis()))
    
    # 6. 测试解说文案生成
    test_results.append(("解说文案生成", await test_narration_script_generation()))
    
    # 输出测试结果
    print("\n" + "="*60)
    print("📊 测试结果汇总:")
    print("="*60)
    
    passed = 0
    total = len(test_results)
    
    for test_name, result in test_results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"  {test_name:<15} {status}")
        if result:
            passed += 1
    
    print(f"\n总计: {passed}/{total} 个测试通过")
    
    if passed == total:
        print("🎉 所有测试通过！LLM服务工作正常。")
    elif passed > 0:
        print("⚠️  部分测试通过，请检查失败的测试项。")
    else:
        print("💥 所有测试失败，请检查配置和网络连接。")
    
    print("="*60)


if __name__ == "__main__":
    # 设置日志级别
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    
    # 运行测试
    asyncio.run(run_all_tests())
