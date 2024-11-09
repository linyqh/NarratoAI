import json
from typing import Dict, Any

def check_format(script_content: str) -> Dict[str, Any]:
    """检查脚本格式
    Args:
        script_content: 脚本内容
    Returns:
        Dict: {'success': bool, 'message': str}
    """
    try:
        # 检查是否为有效的JSON
        data = json.loads(script_content)
        
        # 检查是否为列表
        if not isinstance(data, list):
            return {
                'success': False,
                'message': '脚本必须是JSON数组格式'
            }
        
        # 检查每个片段
        for i, clip in enumerate(data):
            # 检查必需字段
            required_fields = ['narration', 'picture', 'timestamp']
            for field in required_fields:
                if field not in clip:
                    return {
                        'success': False,
                        'message': f'第{i+1}个片段缺少必需字段: {field}'
                    }
            
            # 检查字段类型
            if not isinstance(clip['narration'], str):
                return {
                    'success': False,
                    'message': f'第{i+1}个片段的narration必须是字符串'
                }
            if not isinstance(clip['picture'], str):
                return {
                    'success': False,
                    'message': f'第{i+1}个片段的picture必须是字符串'
                }
            if not isinstance(clip['timestamp'], str):
                return {
                    'success': False,
                    'message': f'第{i+1}个片段的timestamp必须是字符串'
                }
            
            # 检查字段内容不能为空
            if not clip['narration'].strip():
                return {
                    'success': False,
                    'message': f'第{i+1}个片段的narration不能为空'
                }
            if not clip['picture'].strip():
                return {
                    'success': False,
                    'message': f'第{i+1}个片段的picture不能为空'
                }
            if not clip['timestamp'].strip():
                return {
                    'success': False,
                    'message': f'第{i+1}个片段的timestamp不能为空'
                }

        return {
            'success': True,
            'message': '脚本格式检查通过'
        }

    except json.JSONDecodeError as e:
        return {
            'success': False,
            'message': f'JSON格式错误: {str(e)}'
        }
    except Exception as e:
        return {
            'success': False,
            'message': f'检查过程中发生错误: {str(e)}'
        }
