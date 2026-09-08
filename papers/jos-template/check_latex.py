#!/usr/bin/env python3
"""
LaTeX 语法检查脚本
检查论文中的常见语法错误
"""

import re
import sys
from pathlib import Path


def check_latex_syntax(file_path):
    """检查 LaTeX 语法"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    errors = []
    warnings = []
    
    # 1. 检查未闭合的环境
    env_pattern = r'\\begin\{(\w+)\}'
    end_pattern = r'\\end\{(\w+)\}'
    
    begins = re.findall(env_pattern, content)
    ends = re.findall(end_pattern, content)
    
    for env in begins:
        if env not in ends:
            errors.append(f"未闭合的环境: \\begin{{{env}}}")
    
    for env in ends:
        if env not in begins:
            errors.append(f"未开始的环境: \\end{{{env}}}")
    
    # 2. 检查未闭合的花括号
    brace_count = 0
    for i, char in enumerate(content):
        if char == '{':
            brace_count += 1
        elif char == '}':
            brace_count -= 1
        
        if brace_count < 0:
            line_num = content[:i].count('\n') + 1
            errors.append(f"第 {line_num} 行: 多余的花括号 '}}'")
            break
    
    if brace_count > 0:
        errors.append(f"花括号未闭合: {brace_count} 个未闭合")
    
    # 3. 检查未闭合的数学模式
    math_patterns = [
        (r'\$', r'\$', '行内数学模式'),
        (r'\\\[', r'\\\]', '行间数学模式'),
        (r'\\\(', r'\\\)', '行内数学模式'),
    ]
    
    for open_pat, close_pat, name in math_patterns:
        opens = len(re.findall(open_pat, content))
        closes = len(re.findall(close_pat, content))
        if opens != closes:
            warnings.append(f"{name}未闭合: {opens} 个开始, {closes} 个结束")
    
    # 4. 检查常见的 LaTeX 命令错误
    common_errors = [
        (r'\\textbf\{[^}]*\}', 'textbf'),
        (r'\\textit\{[^}]*\}', 'textit'),
        (r'\\emph\{[^}]*\}', 'emph'),
    ]
    
    for pattern, cmd in common_errors:
        matches = re.findall(pattern, content)
        for match in matches:
            # 检查嵌套
            if match.count('{') != match.count('}'):
                warnings.append(f"{cmd} 命令花括号不匹配")
    
    # 5. 检查表格环境
    table_pattern = r'\\begin\{table\}.*?\\end\{table\}'
    tables = re.findall(table_pattern, content, re.DOTALL)
    for i, table in enumerate(tables):
        if '\\caption' not in table:
            warnings.append(f"表格 {i+1} 缺少 \\caption")
        if '\\label' not in table:
            warnings.append(f"表格 {i+1} 缺少 \\label")
    
    # 6. 检查图片环境
    figure_pattern = r'\\begin\{figure\}.*?\\end\{figure\}'
    figures = re.findall(figure_pattern, content, re.DOTALL)
    for i, fig in enumerate(figures):
        if '\\caption' not in fig:
            warnings.append(f"图片 {i+1} 缺少 \\caption")
        if '\\label' not in fig:
            warnings.append(f"图片 {i+1} 缺少 \\label")
    
    # 7. 检查引用
    cite_pattern = r'\\cite\{([^}]+)\}'
    cites = re.findall(cite_pattern, content)
    
    bib_pattern = r'@(\w+)\{([^,]+),'
    bib_entries = re.findall(bib_pattern, content)
    bib_keys = [entry[1] for entry in bib_entries]
    
    for cite in cites:
        keys = [k.strip() for k in cite.split(',')]
        for key in keys:
            if key not in bib_keys:
                warnings.append(f"引用 {key} 未在参考文献中找到")
    
    return errors, warnings


def check_content_quality(file_path):
    """检查内容质量"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    issues = []
    
    # 1. 检查中英文混用
    # (这个检查比较简单，实际应该用更复杂的NLP方法)
    
    # 2. 检查术语一致性
    terms = {
        'Agent': ['agent', 'Agent'],
        'MAREF': ['maref', 'MAREF'],
        'TLA+': ['tla+', 'TLA+'],
    }
    
    for term, variants in terms.items():
        count = sum(content.count(v) for v in variants)
        if count > 0 and count < 3:
            issues.append(f"术语 '{term}' 出现次数较少 ({count} 次)")
    
    # 3. 检查段落长度
    paragraphs = content.split('\n\n')
    for i, para in enumerate(paragraphs):
        if len(para) > 1000:  # 超过1000字符
            issues.append(f"段落 {i+1} 过长 ({len(para)} 字符)")
    
    return issues


def main():
    if len(sys.argv) < 2:
        print("用法: python3 check_latex.py <file.tex>")
        sys.exit(1)
    
    file_path = sys.argv[1]
    
    if not Path(file_path).exists():
        print(f"文件不存在: {file_path}")
        sys.exit(1)
    
    print("=" * 60)
    print("  LaTeX 语法检查报告")
    print("=" * 60)
    print(f"文件: {file_path}")
    print()
    
    # 语法检查
    errors, warnings = check_latex_syntax(file_path)
    
    print("【语法检查】")
    if errors:
        print(f"  错误: {len(errors)} 个")
        for err in errors:
            print(f"    ❌ {err}")
    else:
        print("  ✅ 无语法错误")
    
    if warnings:
        print(f"  警告: {len(warnings)} 个")
        for warn in warnings:
            print(f"    ⚠️  {warn}")
    
    print()
    
    # 内容质量检查
    issues = check_content_quality(file_path)
    
    print("【内容质量】")
    if issues:
        print(f"  问题: {len(issues)} 个")
        for issue in issues:
            print(f"    ⚠️  {issue}")
    else:
        print("  ✅ 内容质量良好")
    
    print()
    
    # 统计信息
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    lines = content.split('\n')
    words = len(content.split())
    
    print("【统计信息】")
    print(f"  总行数: {len(lines)}")
    print(f"  总词数: {words}")
    print(f"  总字符数: {len(content)}")
    
    print()
    print("=" * 60)
    
    # 返回状态
    if errors:
        print("❌ 编译可能失败，请修复错误后重试")
        sys.exit(1)
    else:
        print("✅ 语法检查通过，可以尝试编译")
        sys.exit(0)


if __name__ == "__main__":
    main()
