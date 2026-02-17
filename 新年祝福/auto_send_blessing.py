#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微信新年祝福自动发送脚本 - 增强版（支持自动切换好友）
使用方法：
1. 打开电脑微信，确保主界面可见
2. 准备好友列表（每行一个好友名称）
3. 运行此脚本
4. 脚本会自动搜索好友并发送祝福
"""

import random
import time
import sys
import os
import json

try:
    import pyautogui
    import pyperclip
    from PIL import ImageGrab
except ImportError:
    print("错误：缺少必要的库")
    print("请先安装依赖：pip install pyautogui pyperclip Pillow")
    sys.exit(1)


class AutoBlessingSender:
    """自动祝福发送器（支持自动切换好友）"""
    
    def __init__(self, blessings_file='blessings.txt', friends_file='friends.txt', config_file='config.json'):
        """
        初始化自动祝福发送器
        
        Args:
            blessings_file: 祝福语文件路径
            friends_file: 好友列表文件路径
            config_file: 配置文件路径
        """
        self.blessings_file = blessings_file
        self.friends_file = friends_file
        self.config_file = config_file
        
        self.blessings = []
        self.friends = []
        self.used_blessings = set()
        self.config = self.load_config()
        
        # 设置pyautogui安全参数
        pyautogui.PAUSE = self.config.get('pause', 0.2)
        pyautogui.FAILSAFE = True
        
        self.load_blessings()
        self.load_friends()
    
    def load_config(self):
        """加载配置文件"""
        default_config = {
            'pause': 0.2,
            'search_delay': 1.5,
            'send_delay': 0.5,
            'friend_interval': 2.0,
            'retry_times': 3
        }
        
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                default_config.update(config)
            except Exception as e:
                print(f"警告：加载配置文件失败，使用默认配置 - {e}")
        
        return default_config
    
    def save_config(self):
        """保存配置文件"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"警告：保存配置文件失败 - {e}")
    
    def load_blessings(self):
        """从文件加载祝福语"""
        try:
            with open(self.blessings_file, 'r', encoding='utf-8') as f:
                self.blessings = [line.strip() for line in f if line.strip()]
            print(f"✓ 成功加载 {len(self.blessings)} 条祝福语")
        except FileNotFoundError:
            print(f"错误：找不到祝福语文件 {self.blessings_file}")
            sys.exit(1)
        except Exception as e:
            print(f"错误：加载祝福语失败 - {e}")
            sys.exit(1)
    
    def load_friends(self):
        """从文件加载好友列表"""
        try:
            if os.path.exists(self.friends_file):
                with open(self.friends_file, 'r', encoding='utf-8') as f:
                    self.friends = [line.strip() for line in f if line.strip()]
                print(f"✓ 成功加载 {len(self.friends)} 个好友")
            else:
                print(f"提示：好友列表文件 {self.friends_file} 不存在")
                print("请先创建好友列表文件，每行一个好友名称")
                self.friends = []
        except Exception as e:
            print(f"错误：加载好友列表失败 - {e}")
            self.friends = []
    
    def get_random_blessing(self, avoid_repeat=True):
        """
        获取随机祝福语
        
        Args:
            avoid_repeat: 是否避免重复发送
            
        Returns:
            随机祝福语字符串
        """
        if not avoid_repeat:
            return random.choice(self.blessings)
        
        # 获取未使用的祝福语
        available = [b for b in self.blessings if b not in self.used_blessings]
        
        if not available:
            print("所有祝福语都已发送过，重置使用记录")
            self.used_blessings.clear()
            available = self.blessings
        
        blessing = random.choice(available)
        self.used_blessings.add(blessing)
        return blessing
    
    def activate_wechat(self):
        """激活微信窗口"""
        print("请确保微信主界面可见...")
        time.sleep(1)
        # 使用快捷键激活微信
        pyautogui.hotkey('alt', 'tab')
        time.sleep(0.5)
    
    def search_friend(self, friend_name):
        """
        搜索好友
        
        Args:
            friend_name: 好友名称
            
        Returns:
            是否成功找到并进入聊天
        """
        print(f"正在搜索好友：{friend_name}")
        
        # 按Ctrl+F打开搜索框
        pyautogui.hotkey('ctrl', 'f')
        time.sleep(self.config['search_delay'])
        
        # 清空搜索框并输入好友名称
        pyautogui.hotkey('ctrl', 'a')
        time.sleep(0.1)
        pyperclip.copy(friend_name)
        time.sleep(0.1)
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(self.config['search_delay'])
        
        # 按回车进入聊天
        pyautogui.press('enter')
        time.sleep(self.config['search_delay'])
        
        return True
    
    def send_message(self, message):
        """
        发送消息
        
        Args:
            message: 要发送的消息内容
            
        Returns:
            是否发送成功
        """
        try:
            # 使用剪贴板发送
            pyperclip.copy(message)
            time.sleep(0.2)
            
            # Ctrl+V 粘贴
            pyautogui.hotkey('ctrl', 'v')
            time.sleep(self.config['send_delay'])
            
            # Enter 发送
            pyautogui.press('enter')
            
            return True
            
        except Exception as e:
            print(f"发送失败：{e}")
            return False
    
    def send_to_friend(self, friend_name, blessing=None):
        """
        向指定好友发送祝福
        
        Args:
            friend_name: 好友名称
            blessing: 祝福语，如果为None则随机选择
            
        Returns:
            是否发送成功
        """
        if blessing is None:
            blessing = self.get_random_blessing()
        
        print(f"\n{'='*50}")
        print(f"好友：{friend_name}")
        print(f"祝福：{blessing}")
        print(f"{'='*50}")
        
        # 搜索好友
        if not self.search_friend(friend_name):
            return False
        
        # 发送祝福
        if self.send_message(blessing):
            print(f"✓ 成功发送给 {friend_name}")
            return True
        else:
            print(f"✗ 发送给 {friend_name} 失败")
            return False
    
    def send_to_all_friends(self, start_index=0, end_index=None):
        """
        向所有好友发送祝福
        
        Args:
            start_index: 开始索引
            end_index: 结束索引（不包含），None表示到最后
        """
        if not self.friends:
            print("错误：好友列表为空")
            print("请先创建 friends.txt 文件，每行一个好友名称")
            return
        
        total = len(self.friends)
        if end_index is None:
            end_index = total
        
        count = end_index - start_index
        
        print(f"\n准备向 {count} 个好友发送祝福")
        print(f"起始位置：{start_index + 1}")
        print(f"结束位置：{end_index}")
        print(f"间隔时间：{self.config['friend_interval']} 秒")
        print("\n请确保：")
        print("1. 微信已打开")
        print("2. 微信主界面可见")
        print("3. 不要移动鼠标或切换窗口")
        print("\n5秒后开始发送...")
        
        # 倒计时
        for i in range(5, 0, -1):
            print(f"{i}...")
            time.sleep(1)
        
        success_count = 0
        failed_friends = []
        
        try:
            for i in range(start_index, end_index):
                friend_name = self.friends[i]
                
                print(f"\n[{i-start_index+1}/{count}] 正在处理第 {i+1}/{total} 个好友")
                
                # 发送祝福
                if self.send_to_friend(friend_name):
                    success_count += 1
                else:
                    failed_friends.append(friend_name)
                
                # 间隔时间（最后一个不需要等待）
                if i < end_index - 1:
                    print(f"等待 {self.config['friend_interval']} 秒后发送下一个...")
                    time.sleep(self.config['friend_interval'])
            
            # 输出统计信息
            print(f"\n{'='*50}")
            print(f"发送完成！")
            print(f"成功：{success_count}/{count}")
            print(f"失败：{len(failed_friends)}")
            
            if failed_friends:
                print(f"\n失败的好友：")
                for friend in failed_friends:
                    print(f"  - {friend}")
            
            print(f"{'='*50}\n")
            
        except KeyboardInterrupt:
            print("\n\n用户中止发送")
            print(f"已发送：{success_count}/{count}")
            print(f"当前位置：{start_index + success_count + 1}")
            print(f"\n如需继续发送，可使用：")
            print(f"python auto_send_blessing.py --resume {start_index + success_count}")
    
    def create_friends_file(self):
        """创建好友列表文件"""
        print("\n请输入好友名称（每行一个，输入空行结束）：")
        friends = []
        
        while True:
            friend = input(f"好友 {len(friends)+1}: ").strip()
            if not friend:
                break
            friends.append(friend)
        
        if friends:
            try:
                with open(self.friends_file, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(friends))
                print(f"\n✓ 已保存 {len(friends)} 个好友到 {self.friends_file}")
            except Exception as e:
                print(f"保存失败：{e}")
        else:
            print("未添加任何好友")
    
    def interactive_mode(self):
        """交互式模式"""
        print("\n" + "="*50)
        print("    微信新年祝福自动发送器 - 增强版")
        print("="*50)
        print("1. 向所有好友发送祝福")
        print("2. 向指定范围好友发送祝福")
        print("3. 创建/编辑好友列表")
        print("4. 查看好友列表")
        print("5. 查看祝福语列表")
        print("6. 测试发送（发送给第一个好友）")
        print("7. 设置参数")
        print("8. 退出")
        
        while True:
            try:
                choice = input("\n请选择操作 (1-8): ").strip()
                
                if choice == '1':
                    self.send_to_all_friends()
                elif choice == '2':
                    if not self.friends:
                        print("好友列表为空，请先创建好友列表")
                        continue
                    
                    print(f"\n当前好友列表共 {len(self.friends)} 个好友")
                    start = input(f"起始位置（1-{len(self.friends)}，默认1）: ").strip()
                    end = input(f"结束位置（1-{len(self.friends)}，默认{len(self.friends)}）: ").strip()
                    
                    try:
                        start = int(start) - 1 if start else 0
                        end = int(end) if end else len(self.friends)
                        
                        if start < 0 or start >= len(self.friends):
                            print("起始位置无效")
                        elif end <= start or end > len(self.friends):
                            print("结束位置无效")
                        else:
                            self.send_to_all_friends(start, end)
                    except ValueError:
                        print("请输入有效的数字")
                        
                elif choice == '3':
                    self.create_friends_file()
                    self.load_friends()
                elif choice == '4':
                    if self.friends:
                        print(f"\n好友列表（共 {len(self.friends)} 个）：")
                        for i, friend in enumerate(self.friends, 1):
                            print(f"{i}. {friend}")
                    else:
                        print("\n好友列表为空")
                elif choice == '5':
                    print(f"\n祝福语列表（共 {len(self.blessings)} 条）：")
                    for i, b in enumerate(self.blessings, 1):
                        print(f"{i}. {b}")
                elif choice == '6':
                    if not self.friends:
                        print("好友列表为空，请先创建好友列表")
                    else:
                        print(f"\n测试发送给好友：{self.friends[0]}")
                        confirm = input("确认发送？(y/n): ").strip().lower()
                        if confirm == 'y':
                            self.send_to_friend(self.friends[0])
                elif choice == '7':
                    print("\n当前参数：")
                    print(f"1. 操作间隔：{self.config['pause']} 秒")
                    print(f"2. 搜索延迟：{self.config['search_delay']} 秒")
                    print(f"3. 发送延迟：{self.config['send_delay']} 秒")
                    print(f"4. 好友间隔：{self.config['friend_interval']} 秒")
                    print(f"5. 重试次数：{self.config['retry_times']}")
                    
                    param = input("\n要修改的参数 (1-5): ").strip()
                    if param == '1':
                        val = input("操作间隔（秒）: ").strip()
                        self.config['pause'] = float(val) if val else 0.2
                    elif param == '2':
                        val = input("搜索延迟（秒）: ").strip()
                        self.config['search_delay'] = float(val) if val else 1.5
                    elif param == '3':
                        val = input("发送延迟（秒）: ").strip()
                        self.config['send_delay'] = float(val) if val else 0.5
                    elif param == '4':
                        val = input("好友间隔（秒）: ").strip()
                        self.config['friend_interval'] = float(val) if val else 2.0
                    elif param == '5':
                        val = input("重试次数: ").strip()
                        self.config['retry_times'] = int(val) if val else 3
                    
                    self.save_config()
                    print("✓ 参数已保存")
                elif choice == '8':
                    print("再见！")
                    break
                else:
                    print("无效选择，请重新输入")
                    
            except KeyboardInterrupt:
                print("\n\n程序已退出")
                break
            except Exception as e:
                print(f"发生错误：{e}")


def main():
    """主函数"""
    # 检查祝福语文件是否存在
    if not os.path.exists('blessings.txt'):
        print("错误：找不到祝福语文件 blessings.txt")
        print("请确保该文件与脚本在同一目录下")
        sys.exit(1)
    
    # 创建发送器
    sender = AutoBlessingSender()
    
    # 如果有命令行参数，执行相应操作
    if len(sys.argv) > 1:
        if sys.argv[1] == '--all':
            # 向所有好友发送
            sender.send_to_all_friends()
        elif sys.argv[1] == '--range':
            # 向指定范围好友发送
            start = int(sys.argv[2]) if len(sys.argv) > 2 else 0
            end = int(sys.argv[3]) if len(sys.argv) > 3 else None
            sender.send_to_all_friends(start, end)
        elif sys.argv[1] == '--resume':
            # 从指定位置继续发送
            start = int(sys.argv[2]) if len(sys.argv) > 2 else 0
            sender.send_to_all_friends(start)
        elif sys.argv[1] == '--friends':
            # 创建好友列表
            sender.create_friends_file()
        elif sys.argv[1] == '--test':
            # 测试发送
            if sender.friends:
                sender.send_to_friend(sender.friends[0])
            else:
                print("好友列表为空")
        else:
            print("使用方法：")
            print("  python auto_send_blessing.py              # 交互式模式")
            print("  python auto_send_blessing.py --all       # 向所有好友发送")
            print("  python auto_send_blessing.py --range N M # 向第N到M个好友发送")
            print("  python auto_send_blessing.py --resume N  # 从第N个好友继续发送")
            print("  python auto_send_blessing.py --friends   # 创建好友列表")
            print("  python auto_send_blessing.py --test      # 测试发送")
    else:
        # 进入交互式模式
        sender.interactive_mode()


if __name__ == '__main__':
    main()
