import sys
from pathlib import Path
import pytest
import yaml

backend_dir = Path(__file__).resolve().parent.parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from agents.loader import AgentTemplateLoader


def test_shared_skill_and_secondary_references_loading():
    """测试从 workspace/skills/ 加载公共技能包，并验证二次披露 references 自动装载"""
    loader = AgentTemplateLoader()
    spec = {
        "skills": ["@skills/trend_analysis"]
    }
    prompt = loader.load_prompt_and_skills("data_analyst", spec)

    # 验证主技能名称与内容被装载
    assert "trend_analysis" in prompt
    assert "短期趋势分析量化 SOP 指南" in prompt

    # 验证 references/ 下的二次披露深度参考被递归装载
    assert "indicators_reference.md" in prompt
    assert "量化趋势指标二次披露与深度参考手册" in prompt
    assert "Bias5" in prompt


def test_private_skill_relative_path_loading():
    """测试加载 Agent 专属私有技能目录或文件"""
    loader = AgentTemplateLoader()
    # 模拟引用当前 Agent 私有目录下的文件
    spec = {
        "skills": ["./skills/trend_analysis_sop.md"]
    }
    prompt = loader.load_prompt_and_skills("data_analyst", spec)
    assert "trend_analysis_sop.md" in prompt


def test_short_name_skill_priority_resolution():
    """测试简写名称解析：公共仓库优先匹配"""
    loader = AgentTemplateLoader()
    spec = {
        "skills": ["financial_data_fetch"]
    }
    prompt = loader.load_prompt_and_skills("data_scraper", spec)
    assert "financial_data_fetch" in prompt
    assert "data_dictionary.md" in prompt
    assert "金融行情数据字典与字段清洗对照表" in prompt
