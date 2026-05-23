"""
AST 语义归一化引擎

Cross-Validator 组件：用于检测语义等价的代码，即使语法不同。
基于 Python AST 的归一化，支持语义指纹生成和等价性检测。

应用场景:
1. 检测 Agent 输出代码的语义等价性
2. 识别代码变换/混淆
3. 跨语言语义比较的基础
"""

from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SemanticFingerprint:
    """语义指纹"""

    hash: str
    ast_structure: str  # 归一化后的 AST 结构描述
    token_sequence: list[str]  # 归一化 token 序列
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "hash": self.hash,
            "ast_structure": self.ast_structure,
            "token_sequence": self.token_sequence,
            "metadata": self.metadata,
        }


class ASTNormalizer:
    """
    AST 归一化器

    将 Python 代码转换为归一化的 AST 表示，消除语法差异但保留语义。
    例如:
    - `x = x + 1` 和 `x += 1` 应该产生相同的指纹
    - 变量名被替换为占位符
    - 常量值保留类型但具体值可能被泛化
    """

    def __init__(self):
        self._placeholder_counter = 0
        self._name_mapping: dict[str, str] = {}

    def normalize(self, source_code: str) -> ast.AST:
        """
        归一化源代码

        Args:
            source_code: Python 源代码字符串

        Returns:
            归一化后的 AST
        """
        # 解析 AST
        tree = ast.parse(source_code)

        # 重置映射
        self._placeholder_counter = 0
        self._name_mapping = {}

        # 归一化
        normalized = self._normalize_node(tree)
        return normalized

    def _normalize_node(self, node: ast.AST) -> ast.AST:
        """递归归一化 AST 节点"""
        if isinstance(node, ast.Name):
            # 变量名 -> 占位符
            return ast.Name(
                id=self._get_placeholder(node.id),
                ctx=node.ctx
            )

        elif isinstance(node, ast.Constant):
            # 常量 -> 保留类型但泛化值
            return self._normalize_constant(node)

        elif isinstance(node, ast.BinOp):
            # 二元操作: a + b -> VAR0 OP VAR1
            return ast.BinOp(
                left=self._normalize_node(node.left),
                op=node.op,
                right=self._normalize_node(node.right)
            )

        elif isinstance(node, ast.AugAssign):
            # 增强赋值: x += 1 -> x = x + 1
            return self._normalize_aug_assign(node)

        elif isinstance(node, ast.Compare):
            # 比较操作
            return ast.Compare(
                left=self._normalize_node(node.left),
                ops=node.ops,
                comparators=[self._normalize_node(c) for c in node.comparators]
            )

        elif isinstance(node, ast.Call):
            # 函数调用
            return ast.Call(
                func=self._normalize_node(node.func),
                args=[self._normalize_node(arg) for arg in node.args],
                keywords=[self._normalize_node(kw) for kw in node.keywords]
            )

        elif isinstance(node, ast.keyword):
            return ast.keyword(
                arg=node.arg,
                value=self._normalize_node(node.value)
            )

        elif isinstance(node, ast.FunctionDef):
            # 函数定义: 归一化函数名和参数名
            return ast.FunctionDef(
                name=self._get_placeholder(node.name),
                args=self._normalize_arguments(node.args),
                body=[self._normalize_node(stmt) for stmt in node.body],
                decorator_list=[self._normalize_node(d) for d in node.decorator_list],
                returns=node.returns,
                type_comment=node.type_comment
            )

        elif isinstance(node, ast.arguments):
            return self._normalize_arguments(node)

        elif isinstance(node, ast.arg):
            return ast.arg(
                arg=self._get_placeholder(node.arg),
                annotation=node.annotation,
                type_comment=node.type_comment
            )

        elif isinstance(node, ast.Assign):
            return ast.Assign(
                targets=[self._normalize_node(t) for t in node.targets],
                value=self._normalize_node(node.value),
                type_comment=node.type_comment
            )

        elif isinstance(node, ast.Return):
            return ast.Return(value=self._normalize_node(node.value) if node.value else None)

        elif isinstance(node, ast.If):
            return ast.If(
                test=self._normalize_node(node.test),
                body=[self._normalize_node(stmt) for stmt in node.body],
                orelse=[self._normalize_node(stmt) for stmt in node.orelse]
            )

        elif isinstance(node, ast.For):
            return ast.For(
                target=self._normalize_node(node.target),
                iter=self._normalize_node(node.iter),
                body=[self._normalize_node(stmt) for stmt in node.body],
                orelse=[self._normalize_node(stmt) for stmt in node.orelse],
                type_comment=node.type_comment
            )

        elif isinstance(node, ast.While):
            return ast.While(
                test=self._normalize_node(node.test),
                body=[self._normalize_node(stmt) for stmt in node.body],
                orelse=[self._normalize_node(stmt) for stmt in node.orelse]
            )

        elif isinstance(node, ast.Attribute):
            return ast.Attribute(
                value=self._normalize_node(node.value),
                attr=node.attr,  # 属性名通常保留（API 调用语义）
                ctx=node.ctx
            )

        elif isinstance(node, ast.Subscript):
            return ast.Subscript(
                value=self._normalize_node(node.value),
                slice=self._normalize_node(node.slice),
                ctx=node.ctx
            )

        elif isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            return type(node)(
                elts=[self._normalize_node(elt) for elt in node.elts],
                ctx=getattr(node, 'ctx', None)
            )

        elif isinstance(node, ast.Dict):
            return ast.Dict(
                keys=[self._normalize_node(k) if k else None for k in node.keys],
                values=[self._normalize_node(v) for v in node.values]
            )

        elif isinstance(node, ast.Expr):
            return ast.Expr(value=self._normalize_node(node.value))

        elif isinstance(node, ast.Module):
            return ast.Module(
                body=[self._normalize_node(stmt) for stmt in node.body],
                type_ignores=node.type_ignores
            )

        # 对其他节点类型进行通用处理
        return self._generic_normalize(node)

    def _normalize_constant(self, node: ast.Constant) -> ast.Constant:
        """归一化常量"""
        value = node.value

        if isinstance(value, bool):
            return ast.Constant(value="<BOOL>")
        elif isinstance(value, int):
            return ast.Constant(value="<INT>")
        elif isinstance(value, float):
            return ast.Constant(value="<FLOAT>")
        elif isinstance(value, str):
            # 字符串常量 -> 保留长度信息但内容泛化
            return ast.Constant(value=f"<STR:{len(value)}>")
        elif value is None:
            return ast.Constant(value=None)
        else:
            return ast.Constant(value=f"<{type(value).__name__.upper()}>")

    def _normalize_aug_assign(self, node: ast.AugAssign) -> ast.Assign:
        """将增强赋值转换为普通赋值"""
        # x += 1 -> x = x + 1
        target = self._normalize_node(node.target)

        return ast.Assign(
            targets=[target],
            value=ast.BinOp(
                left=target,
                op=node.op,
                right=self._normalize_node(node.value)
            )
        )

    def _normalize_arguments(self, node: ast.arguments) -> ast.arguments:
        """归一化函数参数"""
        return ast.arguments(
            posonlyargs=[self._normalize_node(arg) for arg in node.posonlyargs],
            args=[self._normalize_node(arg) for arg in node.args],
            vararg=self._normalize_node(node.vararg) if node.vararg else None,
            kwonlyargs=[self._normalize_node(arg) for arg in node.kwonlyargs],
            kw_defaults=[self._normalize_node(d) if d else None for d in node.kw_defaults],
            defaults=[self._normalize_node(d) for d in node.defaults],
            kwarg=self._normalize_node(node.kwarg) if node.kwarg else None,
        )

    def _get_placeholder(self, name: str) -> str:
        """获取或创建变量名的占位符"""
        if name not in self._name_mapping:
            self._name_mapping[name] = f"VAR{self._placeholder_counter}"
            self._placeholder_counter += 1
        return self._name_mapping[name]

    def _generic_normalize(self, node: ast.AST) -> ast.AST:
        """通用归一化 - 对未知节点类型进行字段遍历"""
        new_node = type(node)()

        for _ast_field, old_value in ast.iter_fields(node):
            if isinstance(old_value, ast.AST):
                new_value = self._normalize_node(old_value)
            elif isinstance(old_value, list):
                new_value = []
                for item in old_value:
                    if isinstance(item, ast.AST):
                        new_value.append(self._normalize_node(item))
                    else:
                        new_value.append(item)
            else:
                new_value = old_value

            setattr(new_node, field, new_value)

        return new_node

    def generate_fingerprint(self, source_code: str) -> SemanticFingerprint:
        """
        生成代码的语义指纹

        Args:
            source_code: Python 源代码

        Returns:
            SemanticFingerprint: 语义指纹
        """
        try:
            normalized_ast = self.normalize(source_code)

            # 生成 AST 结构描述
            structure = self._ast_to_structure(normalized_ast)

            # 生成 token 序列
            tokens = self._extract_tokens(normalized_ast)

            # 计算指纹哈希
            fingerprint_data = structure + "".join(tokens)
            hash_value = hashlib.sha256(fingerprint_data.encode()).hexdigest()

            return SemanticFingerprint(
                hash=hash_value,
                ast_structure=structure,
                token_sequence=tokens,
                metadata={
                    "source_length": len(source_code),
                    "normalized": True,
                    "language": "python",
                }
            )
        except SyntaxError as e:
            # 无法解析的代码返回错误指纹
            return SemanticFingerprint(
                hash="",
                ast_structure="",
                token_sequence=[],
                metadata={
                    "error": f"SyntaxError: {e}",
                    "source_length": len(source_code),
                }
            )

    def _ast_to_structure(self, node: ast.AST) -> str:
        """将 AST 转换为结构描述字符串"""
        if isinstance(node, ast.Module):
            parts = [self._ast_to_structure(stmt) for stmt in node.body]
            return "Module(" + ",".join(parts) + ")"
        elif isinstance(node, ast.FunctionDef):
            parts = [self._ast_to_structure(stmt) for stmt in node.body]
            return f"FuncDef({','.join(parts)})"
        elif isinstance(node, ast.Assign):
            parts = [self._ast_to_structure(t) for t in node.targets]
            parts.append(self._ast_to_structure(node.value))
            return f"Assign({','.join(parts)})"
        elif isinstance(node, ast.Return):
            return f"Return({self._ast_to_structure(node.value) if node.value else ''})"
        elif isinstance(node, ast.BinOp):
            op_name = type(node.op).__name__
            return f"BinOp({op_name},{self._ast_to_structure(node.left)},{self._ast_to_structure(node.right)})"
        elif isinstance(node, ast.Name):
            return f"Name({node.id})"
        elif isinstance(node, ast.Constant):
            return f"Const({node.value})"
        elif isinstance(node, ast.Call):
            args = [self._ast_to_structure(arg) for arg in node.args]
            return f"Call({self._ast_to_structure(node.func)},{','.join(args)})"
        elif isinstance(node, ast.If):
            parts = [self._ast_to_structure(node.test)]
            parts.extend(self._ast_to_structure(stmt) for stmt in node.body)
            return f"If({','.join(parts)})"
        elif isinstance(node, ast.For):
            return f"For({self._ast_to_structure(node.target)},{self._ast_to_structure(node.iter)})"
        elif isinstance(node, ast.While):
            return f"While({self._ast_to_structure(node.test)})"
        elif isinstance(node, ast.Compare):
            ops = ",".join(type(op).__name__ for op in node.ops)
            return f"Compare({ops},{self._ast_to_structure(node.left)})"
        elif isinstance(node, ast.Attribute):
            return f"Attr({self._ast_to_structure(node.value)},{node.attr})"
        elif isinstance(node, ast.Subscript):
            return f"Subscript({self._ast_to_structure(node.value)},{self._ast_to_structure(node.slice)})"
        elif isinstance(node, ast.List):
            elts = [self._ast_to_structure(elt) for elt in node.elts]
            return f"List({','.join(elts)})"
        else:
            return type(node).__name__

    def _extract_tokens(self, node: ast.AST) -> list[str]:
        """从 AST 提取归一化 token 序列"""
        tokens: list[str] = []

        for child in ast.walk(node):
            if isinstance(child, ast.Name):
                tokens.append(f"NAME:{child.id}")
            elif isinstance(child, ast.Constant):
                tokens.append(f"CONST:{child.value}")
            elif isinstance(child, ast.BinOp):
                tokens.append(f"OP:{type(child.op).__name__}")
            elif isinstance(child, ast.Call):
                tokens.append("CALL")
            elif isinstance(child, ast.Assign):
                tokens.append("ASSIGN")
            elif isinstance(child, ast.Return):
                tokens.append("RETURN")
            elif isinstance(child, ast.If):
                tokens.append("IF")
            elif isinstance(child, ast.For):
                tokens.append("FOR")
            elif isinstance(child, ast.While):
                tokens.append("WHILE")
            elif isinstance(child, ast.FunctionDef):
                tokens.append("DEF")
            elif isinstance(child, ast.Compare):
                tokens.append("CMP")

        return tokens


class SemanticEquivalenceChecker:
    """语义等价性检查器"""

    def __init__(self):
        self.normalizer = ASTNormalizer()

    def check_equivalence(
        self,
        code_a: str,
        code_b: str,
        threshold: float = 0.95
    ) -> dict[str, Any]:
        """
        检查两段代码是否语义等价

        Args:
            code_a: 代码 A
            code_b: 代码 B
            threshold: 等价判定阈值 (0.0-1.0)

        Returns:
            包含等价性判断结果的字典
        """
        fp_a = self.normalizer.generate_fingerprint(code_a)
        fp_b = self.normalizer.generate_fingerprint(code_b)

        # 如果指纹完全相同
        if fp_a.hash and fp_a.hash == fp_b.hash:
            return {
                "equivalent": True,
                "similarity": 1.0,
                "method": "exact_fingerprint_match",
                "fingerprint_a": fp_a.hash[:16] if fp_a.hash else None,
                "fingerprint_b": fp_b.hash[:16] if fp_b.hash else None,
            }

        # 计算结构相似度
        structure_sim = self._structure_similarity(
            fp_a.ast_structure, fp_b.ast_structure
        )

        # 计算 token 序列相似度
        token_sim = self._token_similarity(
            fp_a.token_sequence, fp_b.token_sequence
        )

        # 综合相似度（加权平均）
        overall_sim = 0.6 * structure_sim + 0.4 * token_sim

        return {
            "equivalent": overall_sim >= threshold,
            "similarity": round(overall_sim, 3),
            "structure_similarity": round(structure_sim, 3),
            "token_similarity": round(token_sim, 3),
            "threshold": threshold,
            "fingerprint_a": fp_a.hash[:16] if fp_a.hash else None,
            "fingerprint_b": fp_b.hash[:16] if fp_b.hash else None,
        }

    def _structure_similarity(self, struct_a: str, struct_b: str) -> float:
        """计算结构相似度（简化版）"""
        if not struct_a or not struct_b:
            return 0.0

        # 使用简单的字符级相似度
        # 生产环境应使用更复杂的树编辑距离
        len_a, len_b = len(struct_a), len(struct_b)
        if len_a == 0 and len_b == 0:
            return 1.0

        # 计算最长公共子序列的近似
        max_len = max(len_a, len_b)
        common = 0
        min_len = min(len_a, len_b)
        for i in range(min_len):
            if struct_a[i] == struct_b[i]:
                common += 1

        return common / max_len

    def _token_similarity(self, tokens_a: list[str], tokens_b: list[str]) -> float:
        """计算 token 序列相似度"""
        if not tokens_a and not tokens_b:
            return 1.0
        if not tokens_a or not tokens_b:
            return 0.0

        # 使用 Jaccard 相似度
        set_a = set(tokens_a)
        set_b = set(tokens_b)

        intersection = len(set_a & set_b)
        union = len(set_a | set_b)

        return intersection / union if union > 0 else 0.0


__all__ = [
    "ASTNormalizer",
    "SemanticEquivalenceChecker",
    "SemanticFingerprint",
]
