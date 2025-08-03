import json
import re
from typing import Dict, Any

def check_format(script_content: str) -> Dict[str, Any]:
    """检查脚本格式
    Args:
        script_content: 脚本内容
    Returns:
        Dict: {'success': bool, 'message': str, 'details': str}
    """
    try:
        # 检查是否为有效的JSON
        data = json.loads(script_content)

        # 检查是否为列表
        if not isinstance(data, list):
            return {
                'success': False,
                'message': '脚本必须是JSON数组格式',
                'details': '正确格式应该是: [{"_id": 1, "timestamp": "...", ...}, ...]'
            }

        # 检查数组不能为空
        if len(data) == 0:
            return {
                'success': False,
                'message': '脚本数组不能为空',
                'details': '至少需要包含一个脚本片段'
            }

        # 检查每个片段
        for i, clip in enumerate(data):
            # 检查是否为对象类型
            if not isinstance(clip, dict):
                return {
                    'success': False,
                    'message': f'第{i+1}个元素必须是对象类型',
                    'details': f'当前类型: {type(clip).__name__}'
                }

            # 检查必需字段
            required_fields = ['_id', 'timestamp', 'picture', 'narration', 'OST']
            for field in required_fields:
                if field not in clip:
                    return {
                        'success': False,
                        'message': f'第{i+1}个片段缺少必需字段: {field}',
                        'details': f'必需字段: {", ".join(required_fields)}'
                    }

            # 验证 _id 字段
            if not isinstance(clip['_id'], int) or clip['_id'] <= 0:
                return {
                    'success': False,
                    'message': f'第{i+1}个片段的_id必须是正整数',
                    'details': f'当前值: {clip["_id"]} (类型: {type(clip["_id"]).__name__})'
                }

            # 验证 timestamp 字段格式
            timestamp_pattern = r'^\d{2}:\d{2}:\d{2},\d{3}-\d{2}:\d{2}:\d{2},\d{3}$'
            if not isinstance(clip['timestamp'], str) or not re.match(timestamp_pattern, clip['timestamp']):
                return {
                    'success': False,
                    'message': f'第{i+1}个片段的timestamp格式错误',
                    'details': f'正确格式: "HH:MM:SS,mmm-HH:MM:SS,mmm"，示例: "00:00:00,600-00:00:07,559"'
                }

            # 验证 picture 字段
            if not isinstance(clip['picture'], str) or not clip['picture'].strip():
                return {
                    'success': False,
                    'message': f'第{i+1}个片段的picture必须是非空字符串',
                    'details': f'当前值: {clip.get("picture", "未定义")}'
                }

            # 验证 narration 字段
            if not isinstance(clip['narration'], str) or not clip['narration'].strip():
                return {
                    'success': False,
                    'message': f'第{i+1}个片段的narration必须是非空字符串',
                    'details': f'当前值: {clip.get("narration", "未定义")}'
                }

            # 验证 OST 字段
            if not isinstance(clip['OST'], int):
                return {
                    'success': False,
                    'message': f'第{i+1}个片段的OST必须是整数',
                    'details': f'当前值: {clip["OST"]} (类型: {type(clip["OST"]).__name__})，常用值: 0, 1, 2'
                }

        return {
            'success': True,
            'message': '脚本格式检查通过',
            'details': f'共验证 {len(data)} 个脚本片段，格式正确'
        }

    except json.JSONDecodeError as e:
        return {
            'success': False,
            'message': f'JSON格式错误: {str(e)}',
            'details': '请检查JSON语法，确保所有括号、引号、逗号正确'
        }
    except Exception as e:
        return {
            'success': False,
            'message': f'检查过程中发生错误: {str(e)}',
            'details': '请联系技术支持'
        }
