#!/usr/bin/env python3
"""使用macOS Mail应用发送邮件 - AppleScript兼容版"""

import subprocess
import os
import tempfile
import time

def send_mail_applescript(to_addr, subject, body_lines):
    """通过AppleScript发送邮件 - 使用paragraphs连接"""
    
    # 将多行文本转换为AppleScript的paragraphs格式
    body_applescript = " & (ASCII character 13) & ".join([f'"{line}"' for line in body_lines])
    
    script = f'''tell application "Mail"
    activate
    set msgBody to {body_applescript}
    set newMessage to make new outgoing message with properties {{subject:"{subject}", content:msgBody}}
    tell newMessage
        make new to recipient at end of to recipients with properties {{address:"{to_addr}"}}
    end tell
    delay 1
    send newMessage
end tell'''
    
    # 写入临时文件
    fd, path = tempfile.mkstemp(suffix='.scpt')
    with os.fdopen(fd, 'w') as f:
        f.write(script)
    
    try:
        result = subprocess.run(
            ['osascript', path],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            print(f"✅ 邮件已创建并发送 -> {to_addr}")
            return True
        else:
            print(f"❌ AppleScript执行失败: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        print(f"❌ AppleScript执行超时")
        return False
    except Exception as e:
        print(f"❌ 执行错误: {e}")
        return False
    finally:
        try:
            os.unlink(path)
        except:
            pass

def main():
    # 邮件1：南山区科技创新局
    nanshan_email = "nsqkjj@szns.gov.cn"
    nanshan_subject = "【咨询】MAREF项目申报南山区开源生态培育行动/重大开源项目"
    nanshan_body = [
        "尊敬的南山区科技创新局领导：",
        "",
        "您好！",
        "",
        "我是MAREF（Multi-Agent Recursive Evolution Framework）项目的技术负责人。MAREF是一个开源的Agent治理操作系统（Agent Governance OS），致力于解决AI Agent的安全治理、协同执行和自主演进问题。",
        "",
        "【项目简介】",
        "- 项目名称：MAREF - 多智能体递归演进框架",
        "- GitHub: https://github.com/maref-org/maref",
        "- 技术栈：Python 3.10+、FastAPI、TLA+形式化验证",
        "- 许可证：Apache-2.0",
        "",
        "【核心技术优势】",
        "1. 六层治理架构 - 首创Agent治理状态机",
        "2. 10状态格雷码治理状态机 - 保证状态切换的安全性和可逆性",
        "3. TLA+形式化验证 - 用数学方法证明系统安全性",
        "4. 递归自演进引擎 - Agent可自主诊断、修复、优化自身",
        "5. 红蓝对抗训练 - 攻防一体，持续安全加固",
        "6. A2A/MCP双协议支持 - 兼容多智能体通信标准",
        "",
        "【开源生态价值】",
        "- 解决AI Agent安全治理的卡脖子问题",
        "- 填补国内外Agent治理操作系统空白",
        "- 为深圳打造人工智能先锋城市提供基础设施",
        "- 已吸引国际社区关注，多名学者愿意背书",
        "",
        "【申报咨询】",
        "我们希望申报南山区开源生态培育行动/深圳市重大开源项目商业发行版软件推广应用项目，请问：",
        "1. 申报条件和时间安排",
        "2. 需要准备的材料清单",
        "3. 是否需要公司注册主体，还是可以以社区/个人名义申报",
        "4. 评审标准和流程",
        "",
        "期待您的回复！",
        "",
        "MAREF 技术团队",
        "2026年6月6日",
        "GitHub: https://github.com/maref-org/maref"
    ]

    # 邮件2：深圳市工业和信息化局
    gongxin_email = "xzc@gxj.sz.gov.cn"
    gongxin_subject = "【咨询】MAREF项目 - 人工智能软件开源奖励项目申报"
    gongxin_body = [
        "尊敬的深圳市工业和信息化局领导：",
        "",
        "您好！",
        "",
        "我是MAREF（Multi-Agent Recursive Evolution Framework）项目的技术负责人。获悉贵局发布的人工智能先锋城市项目中有人工智能软件开源奖励项目（一等最高100万，二等最高60万），特此咨询。",
        "",
        "【项目简介】",
        "- 项目名称：MAREF - 多智能体递归演进框架",
        "- GitHub: https://github.com/maref-org/maref",
        "- 定位：开源的Agent治理操作系统（Agent Governance OS）",
        "- 许可证：Apache-2.0",
        "",
        "【核心技术】",
        "1. 六层治理架构 - 首创Agent治理状态机",
        "2. TLA+形式化验证 - 数学方法证明系统安全性",
        "3. 递归自演进引擎 - Agent可自主诊断、修复、优化",
        "4. 红蓝对抗训练 - 攻防一体持续安全加固",
        "",
        "【申报咨询】",
        "1. 开源项目是否可以先以社区名义申报，后续注册公司后补充材料？",
        "2. 申报截止时间和材料清单",
        "3. 评审标准中对开源项目的特殊要求",
        "4. 下载量/性能/影响力的评估标准",
        "",
        "期待您的指导！",
        "",
        "MAREF 技术团队",
        "2026年6月6日",
        "GitHub: https://github.com/maref-org/maref"
    ]

    # 邮件3：深圳OPC创业社区
    opc_email = "opcchina@opcfoundation.org"
    opc_subject = "【咨询】MAREF项目入驻深圳OPC创业社区申请"
    opc_body = [
        "尊敬的深圳OPC创业社区运营团队：",
        "",
        "您好！",
        "",
        "我是MAREF（Multi-Agent Recursive Evolution Framework）项目的技术负责人。获悉深圳市正在打造人工智能OPC创业生态引领地，特此咨询入驻事宜。",
        "",
        "【项目简介】",
        "- 项目名称：MAREF - 多智能体递归演进框架",
        "- GitHub: https://github.com/maref-org/maref",
        "- 定位：开源的Agent治理操作系统（Agent Governance OS）",
        "- 许可证：Apache-2.0",
        "",
        "【团队情况】",
        "- 团队形态：OPC（一人公司）/小型科创团队",
        "- 技术底色：AI驱动项目，已有可演示原型/MVP",
        "- 领域聚焦：AI Agent安全治理、多智能体协同、自主演进系统",
        "- 创始人背景：技术极客，具备商业嗅觉和快速进化能力",
        "",
        "【核心技术】",
        "1. 六层治理架构 - 首创Agent治理状态机",
        "2. TLA+形式化验证 - 数学方法证明系统安全性",
        "3. 递归自演进引擎 - Agent可自主诊断、修复、优化",
        "4. 红蓝对抗训练 - 攻防一体持续安全加固",
        "",
        "【入驻咨询】",
        "1. 南山区/龙岗区/福田区哪个OPC社区更适合AI软件项目？",
        "2. 入驻申请流程和所需材料",
        "3. 是否有租金补贴/青年驿站/打样券等扶持政策？",
        "4. 社区提供哪些产业生态资源对接？",
        "",
        "期待您的回复！",
        "",
        "MAREF 技术团队",
        "2026年6月6日",
        "GitHub: https://github.com/maref-org/maref"
    ]

    print("=" * 50)
    print("开始发送MAREF项目申报咨询邮件")
    print("=" * 50)

    success_count = 0

    # 发送南山区科创局邮件
    print("\n📧 发送南山区科技创新局咨询邮件...")
    if send_mail_applescript(nanshan_email, nanshan_subject, nanshan_body):
        success_count += 1
        time.sleep(2)  # 等待邮件应用处理

    # 发送深圳市工信局邮件
    print("\n📧 发送深圳市工业和信息化局咨询邮件...")
    if send_mail_applescript(gongxin_email, gongxin_subject, gongxin_body):
        success_count += 1
        time.sleep(2)

    # 发送OPC社区邮件
    print("\n📧 发送深圳OPC创业社区入驻咨询邮件...")
    if send_mail_applescript(opc_email, opc_subject, opc_body):
        success_count += 1
        time.sleep(2)

    print("\n" + "=" * 50)
    print(f"邮件发送完成：{success_count}/3 成功")
    print("=" * 50)


if __name__ == "__main__":
    main()
