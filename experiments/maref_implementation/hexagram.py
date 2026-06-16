"""
64卦状态系统 - MAREF智能工作流契约框架核心组件
基于《易经》64卦的二进制表示，实现最小完备状态空间（2^6=64）
设计原则：格雷编码拓扑、斯佩纳完备性、控制论观察
"""

from dataclasses import dataclass


@dataclass
class Hexagram:
    """64卦状态表示"""

    binary: str  # 6位二进制，如"111111"
    name: str  # 卦名，如"乾"
    symbol: str  # 卦符号，如"䷀"
    description: str  # 卦描述

    def __post_init__(self):
        """验证卦状态的有效性"""
        if len(self.binary) != 6:
            raise ValueError(f"二进制长度必须为6位: {self.binary}")
        if any(c not in "01" for c in self.binary):
            raise ValueError(f"二进制只能包含0或1: {self.binary}")

    @classmethod
    def from_binary(cls, binary: str) -> "Hexagram":
        """从二进制创建卦对象"""
        # 验证6位二进制
        if len(binary) != 6 or any(c not in "01" for c in binary):
            raise ValueError(f"无效的二进制表示: {binary}")

        # 映射到64卦
        hexagram_data = HEXAGRAM_DATA.get(binary)
        if not hexagram_data:
            raise ValueError(f"未找到对应64卦的二进制: {binary}")

        return cls(
            binary=binary,
            name=hexagram_data["name"],
            symbol=hexagram_data["symbol"],
            description=hexagram_data["description"],
        )

    @classmethod
    def from_decimal(cls, decimal: int) -> "Hexagram":
        """从十进制数创建卦对象 (0-63)"""
        if decimal < 0 or decimal > 63:
            raise ValueError(f"十进制数必须在0-63范围内: {decimal}")

        # 转换为6位二进制
        binary = format(decimal, "06b")
        return cls.from_binary(binary)

    def to_decimal(self) -> int:
        """转换为十进制数 (0-63)"""
        return int(self.binary, 2)

    def hamming_distance(self, other: "Hexagram") -> int:
        """计算与另一个卦的汉明距离"""
        return sum(c1 != c2 for c1, c2 in zip(self.binary, other.binary, strict=False))

    def is_valid_transition(self, to_state: "Hexagram") -> bool:
        """验证是否为合法的格雷编码转换（汉明距离=1）"""
        return self.hamming_distance(to_state) == 1

    def flip_bit(self, position: int) -> "Hexagram":
        """翻转指定位置的比特位（0-based索引）"""
        if position < 0 or position >= 6:
            raise ValueError(f"位置必须在0-5范围内: {position}")

        binary_list = list(self.binary)
        binary_list[position] = "1" if binary_list[position] == "0" else "0"
        new_binary = "".join(binary_list)

        return Hexagram.from_binary(new_binary)

    def get_complement(self) -> "Hexagram":
        """获取互补卦（错卦）- 所有比特位取反"""
        complement_binary = "".join("1" if bit == "0" else "0" for bit in self.binary)
        return Hexagram.from_binary(complement_binary)

    def get_mirror(self) -> "Hexagram":
        """获取镜像卦（综卦）- 比特位逆序"""
        mirror_binary = self.binary[::-1]
        return Hexagram.from_binary(mirror_binary)

    def __str__(self):
        return f"{self.symbol} {self.name} ({self.binary}): {self.description}"

    def __eq__(self, other):
        if not isinstance(other, Hexagram):
            return False
        return self.binary == other.binary

    def __hash__(self):
        return hash(self.binary)


# 64卦数据映射表
HEXAGRAM_DATA = {
    # 纯阳至纯阴
    "111111": {"name": "乾", "symbol": "䷀", "description": "天行健，君子以自强不息"},
    "000000": {"name": "坤", "symbol": "䷁", "description": "地势坤，君子以厚德载物"},
    # 上经30卦
    "100010": {"name": "屯", "symbol": "䷂", "description": "云雷屯，君子以经纶"},
    "010001": {"name": "蒙", "symbol": "䷃", "description": "山下出泉，蒙；君子以果行育德"},
    "111010": {"name": "需", "symbol": "䷄", "description": "云上于天，需；君子以饮食宴乐"},
    "010111": {"name": "讼", "symbol": "䷅", "description": "天与水违行，讼；君子以作事谋始"},
    "010000": {"name": "师", "symbol": "䷆", "description": "地中有水，师；君子以容民畜众"},
    "000010": {"name": "比", "symbol": "䷇", "description": "地上有水，比；先王以建万国，亲诸侯"},
    "111011": {"name": "小畜", "symbol": "䷈", "description": "风行天上，小畜；君子以懿文德"},
    "110111": {"name": "履", "symbol": "䷉", "description": "上天下泽，履；君子以辩上下，定民志"},
    "111000": {
        "name": "泰",
        "symbol": "䷊",
        "description": "天地交，泰；后以财成天地之道，辅相天地之宜",
    },
    "000111": {
        "name": "否",
        "symbol": "䷋",
        "description": "天地不交，否；君子以俭德辟难，不可荣以禄",
    },
    "101111": {"name": "同人", "symbol": "䷌", "description": "天与火，同人；君子以类族辨物"},
    "111101": {
        "name": "大有",
        "symbol": "䷍",
        "description": "火在天上，大有；君子以遏恶扬善，顺天休命",
    },
    "001000": {
        "name": "谦",
        "symbol": "䷎",
        "description": "地中有山，谦；君子以裒多益寡，称物平施",
    },
    "000100": {
        "name": "豫",
        "symbol": "䷏",
        "description": "雷出地奋，豫；先王以作乐崇德，殷荐之上帝",
    },
    "100110": {"name": "随", "symbol": "䷐", "description": "泽中有雷，随；君子以向晦入宴息"},
    "011001": {"name": "蛊", "symbol": "䷑", "description": "山下有风，蛊；君子以振民育德"},
    "110000": {
        "name": "临",
        "symbol": "䷒",
        "description": "泽上有地，临；君子以教思无穷，容保民无疆",
    },
    "000011": {"name": "观", "symbol": "䷓", "description": "风行地上，观；先王以省方观民设教"},
    "100101": {"name": "噬嗑", "symbol": "䷔", "description": "雷电噬嗑；先王以明罚敕法"},
    "101001": {"name": "贲", "symbol": "䷕", "description": "山下有火，贲；君子以明庶政，无敢折狱"},
    "000001": {"name": "剥", "symbol": "䷖", "description": "山附于地，剥；上以厚下安宅"},
    "100000": {
        "name": "复",
        "symbol": "䷗",
        "description": "雷在地中，复；先王以至日闭关，商旅不行",
    },
    "100111": {
        "name": "无妄",
        "symbol": "䷘",
        "description": "天下雷行，物与无妄；先王以茂对时育万物",
    },
    "111001": {
        "name": "大畜",
        "symbol": "䷙",
        "description": "天在山中，大畜；君子以多识前言往行，以畜其德",
    },
    "100001": {"name": "颐", "symbol": "䷚", "description": "山下有雷，颐；君子以慎言语，节饮食"},
    "011110": {
        "name": "大过",
        "symbol": "䷛",
        "description": "泽灭木，大过；君子以独立不惧，遁世无闷",
    },
    "010010": {"name": "坎", "symbol": "䷜", "description": "水洊至，习坎；君子以常德行，习教事"},
    "101010": {"name": "离", "symbol": "䷝", "description": "明两作，离；大人以继明照于四方"},
    # 下经34卦
    "001110": {"name": "咸", "symbol": "䷞", "description": "山上有泽，咸；君子以虚受人"},
    "011100": {"name": "恒", "symbol": "䷟", "description": "雷风，恒；君子以立不易方"},
    "111100": {"name": "遁", "symbol": "䷠", "description": "天下有山，遁；君子以远小人，不恶而严"},
    "001111": {"name": "大壮", "symbol": "䷡", "description": "雷在天上，大壮；君子以非礼弗履"},
    "000101": {"name": "晋", "symbol": "䷢", "description": "明出地上，晋；君子以自昭明德"},
    "101000": {
        "name": "明夷",
        "symbol": "䷣",
        "description": "明入地中，明夷；君子以莅众，用晦而明",
    },
    "101011": {
        "name": "家人",
        "symbol": "䷤",
        "description": "风自火出，家人；君子以言有物而行有恒",
    },
    "110101": {"name": "睽", "symbol": "䷥", "description": "上火下泽，睽；君子以同而异"},
    "001010": {"name": "蹇", "symbol": "䷦", "description": "山上有水，蹇；君子以反身修德"},
    "010100": {"name": "解", "symbol": "䷧", "description": "雷雨作，解；君子以赦过宥罪"},
    "110001": {"name": "损", "symbol": "䷨", "description": "山下有泽，损；君子以惩忿窒欲"},
    "100011": {"name": "益", "symbol": "䷩", "description": "风雷，益；君子以见善则迁，有过则改"},
    "111110": {
        "name": "夬",
        "symbol": "䷪",
        "description": "泽上于天，夬；君子以施禄及下，居德则忌",
    },
    "011111": {"name": "姤", "symbol": "䷫", "description": "天下有风，姤；后以施命诰四方"},
    "000110": {"name": "萃", "symbol": "䷬", "description": "泽上于地，萃；君子以除戎器，戒不虞"},
    "011000": {"name": "升", "symbol": "䷭", "description": "地中生木，升；君子以顺德，积小以高大"},
    "010110": {"name": "困", "symbol": "䷮", "description": "泽无水，困；君子以致命遂志"},
    "011010": {"name": "井", "symbol": "䷯", "description": "木上有水，井；君子以劳民劝相"},
    "101100": {"name": "革", "symbol": "䷰", "description": "泽中有火，革；君子以治历明时"},
    "001101": {"name": "鼎", "symbol": "䷱", "description": "木上有火，鼎；君子以正位凝命"},
    "100100": {"name": "震", "symbol": "䷲", "description": "洊雷，震；君子以恐惧修省"},
    "001001": {"name": "艮", "symbol": "䷳", "description": "兼山，艮；君子以思不出其位"},
    "001011": {"name": "渐", "symbol": "䷴", "description": "山上有木，渐；君子以居贤德善俗"},
    "110100": {"name": "归妹", "symbol": "䷵", "description": "泽上有雷，归妹；君子以永终知敝"},
    "101110": {"name": "丰", "symbol": "䷶", "description": "雷电皆至，丰；君子以折狱致刑"},
    "011101": {"name": "旅", "symbol": "䷷", "description": "山上有火，旅；君子以明慎用刑而不留狱"},
    "011011": {"name": "巽", "symbol": "䷸", "description": "随风，巽；君子以申命行事"},
    "110110": {"name": "兑", "symbol": "䷹", "description": "丽泽，兑；君子以朋友讲习"},
    "010011": {"name": "涣", "symbol": "䷺", "description": "风行水上，涣；先王以享于帝，立庙"},
    "110010": {"name": "节", "symbol": "䷻", "description": "泽上有水，节；君子以制数度，议德行"},
    "110011": {"name": "中孚", "symbol": "䷼", "description": "泽上有风，中孚；君子以议狱缓死"},
    "001100": {
        "name": "小过",
        "symbol": "䷽",
        "description": "山上有雷，小过；君子以行过乎恭，丧过乎哀，用过乎俭",
    },
    "101101": {"name": "既济", "symbol": "䷾", "description": "水在火上，既济；君子以思患而豫防之"},
    "010101": {"name": "未济", "symbol": "䷿", "description": "火在水上，未济；君子以慎辨物居方"},
}

# 创建64卦集合
HEXAGRAMS_64 = {Hexagram.from_binary(binary) for binary in HEXAGRAM_DATA}


def get_hexagram_by_name(name: str) -> Hexagram | None:
    """根据卦名获取卦对象"""
    for binary, data in HEXAGRAM_DATA.items():
        if data["name"] == name:
            return Hexagram.from_binary(binary)
    return None


def get_hexagram_by_symbol(symbol: str) -> Hexagram | None:
    """根据卦符号获取卦对象"""
    for binary, data in HEXAGRAM_DATA.items():
        if data["symbol"] == symbol:
            return Hexagram.from_binary(binary)
    return None


def generate_gray_code_sequence(start: int, end: int) -> list[int]:
    """
    生成格雷编码序列（start到end）
    格雷编码：相邻数字的二进制表示仅有一位不同
    """

    def gray_code(n: int) -> int:
        return n ^ (n >> 1)

    sequence = []
    for i in range(min(start, end), max(start, end) + 1):
        sequence.append(gray_code(i))

    if start > end:
        sequence.reverse()

    return sequence


def binary_gray_code_transform(from_bits: str, to_bits: str) -> list[str]:
    """
    计算从from_bits到to_bits的格雷编码转换路径
    确保每次只改变一位比特（汉明距离=1）
    """
    if len(from_bits) != len(to_bits):
        raise ValueError(f"二进制长度不一致: {len(from_bits)} vs {len(to_bits)}")

    from_int = int(from_bits, 2)
    to_int = int(to_bits, 2)

    if from_int == to_int:
        return [from_bits]

    # 生成格雷编码路径
    gray_path = generate_gray_code_sequence(from_int, to_int)

    # 转换为二进制字符串
    path_bits = []
    for num in gray_path:
        # 转换为固定长度的二进制字符串
        binary = format(num, f"0{len(from_bits)}b")
        path_bits.append(binary)

    return path_bits
