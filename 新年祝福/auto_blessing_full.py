#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微信新年祝福全自动发送脚本
=============================
使用 Windows UI Automation 直接操控微信客户端，实现：
1. 自动获取微信通讯录中的所有好友
2. 自动逐个发送随机不重复的新年祝福
3. 发送进度持久化，支持断点续发
4. 排除列表支持（公众号、群聊、特定好友）
5. 全程无需手动干预

依赖安装：
    pip install uiautomation pyperclip

使用方法：
    python auto_blessing_full.py              # 全自动：获取好友 + 发送祝福
    python auto_blessing_full.py --fetch      # 仅获取好友列表
    python auto_blessing_full.py --send       # 仅发送祝福（使用已有好友列表）
    python auto_blessing_full.py --resume     # 断点续发
    python auto_blessing_full.py --status     # 查看发送进度
    python auto_blessing_full.py --dry-run    # 模拟运行（不实际发送）
    python auto_blessing_full.py --reset      # 重置发送进度
"""

import os
import sys
import json
import time
import random
import logging
import argparse
from datetime import datetime
from typing import List, Dict, Optional, Set

# ─── 依赖检查 ───────────────────────────────────────────────────────────────

def check_dependencies():
    """检查并导入依赖库"""
    missing = []
    try:
        import uiautomation  # noqa: F401
    except ImportError:
        missing.append('uiautomation')
    try:
        import pyperclip  # noqa: F401
    except ImportError:
        missing.append('pyperclip')
    if missing:
        print("❌ 缺少必要的库，请先安装：")
        print(f"   pip install {' '.join(missing)}")
        sys.exit(1)


check_dependencies()

import uiautomation as auto
import pyperclip

# ─── 日志配置 ───────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('auto_blessing.log', encoding='utf-8'),
    ]
)
logger = logging.getLogger(__name__)

# ─── 常量 ─────────────────────────────────────────────────────────────────

BLESSINGS_FILE = 'blessings.txt'
FRIENDS_FILE = 'friends.txt'
PROGRESS_FILE = 'send_progress.json'
EXCLUDE_FILE = 'exclude_list.txt'

# 默认排除关键词（公众号、系统账号等）
DEFAULT_EXCLUDE_KEYWORDS = [
    '微信团队', '文件传输助手', '微信支付', '腾讯新闻',
    '朋友圈', '服务通知', '订阅号消息', '微信运动',
    '腾讯客服', '微信游戏',
]


# ─── 工具函数 ──────────────────────────────────────────────────────────────

def load_text_lines(filepath: str) -> List[str]:
    """从文本文件加载非空行列表"""
    if not os.path.exists(filepath):
        return []
    with open(filepath, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]


def save_text_lines(filepath: str, lines: List[str]):
    """保存列表到文本文件（每行一条）"""
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')


def load_json(filepath: str) -> dict:
    """加载 JSON 文件"""
    if not os.path.exists(filepath):
        return {}
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_json(filepath: str, data: dict):
    """保存 JSON 文件"""
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ─── 微信自动化核心类 ──────────────────────────────────────────────────────

class WeChatAutomation:
    """微信 UI 自动化操控"""

    def __init__(self):
        self.wechat_window: Optional[auto.WindowControl] = None

    def find_wechat(self) -> bool:
        """查找并激活微信主窗口"""
        logger.info("正在查找微信窗口...")
        try:
            self.wechat_window = auto.WindowControl(
                searchDepth=1, ClassName='WeChatMainWndForPC'
            )
            if not self.wechat_window.Exists(maxSearchSeconds=5):
                # 尝试备用类名
                self.wechat_window = auto.WindowControl(
                    searchDepth=1, Name='微信'
                )
                if not self.wechat_window.Exists(maxSearchSeconds=5):
                    logger.error("未找到微信窗口，请确保微信已打开")
                    return False

            # 激活窗口
            self.wechat_window.SetActive()
            self.wechat_window.SetFocus()
            time.sleep(0.5)
            logger.info("✅ 已找到微信窗口: %s", self.wechat_window.Name)
            return True
        except Exception as e:
            logger.error("查找微信窗口失败: %s", e)
            return False

    def switch_to_contacts(self) -> bool:
        """切换到通讯录页面"""
        if not self.wechat_window:
            return False
        try:
            self.wechat_window.SetActive()
            time.sleep(0.3)

            # 方案1：点击通讯录按钮
            contact_btn = self.wechat_window.ButtonControl(Name='通讯录')
            if contact_btn.Exists(maxSearchSeconds=3):
                contact_btn.Click()
                time.sleep(1)
                logger.info("✅ 已切换到通讯录页面")
                return True

            # 方案2：通过导航栏查找
            nav_items = self.wechat_window.ListControl(Name='导航')
            if nav_items.Exists(maxSearchSeconds=2):
                items = nav_items.GetChildren()
                if len(items) >= 2:
                    items[1].Click()
                    time.sleep(1)
                    logger.info("✅ 已切换到通讯录页面（通过导航栏）")
                    return True

            logger.warning("未找到通讯录按钮，尝试使用快捷键...")
            auto.SendKeys('{Ctrl}{Shift}c')
            time.sleep(1)
            return True
        except Exception as e:
            logger.error("切换到通讯录失败: %s", e)
            return False

    def get_all_friends_from_contacts(self) -> List[str]:
        """
        从通讯录页面获取所有好友名称。
        通过滚动通讯录列表逐步获取。
        """
        if not self.wechat_window:
            return []

        friends: List[str] = []
        seen: Set[str] = set()

        logger.info("正在从通讯录获取好友列表...")

        try:
            # 查找通讯录列表控件
            contact_list = self.wechat_window.ListControl(Name='联系人')
            if not contact_list.Exists(maxSearchSeconds=5):
                contact_list = self.wechat_window.ListControl()
                if not contact_list.Exists(maxSearchSeconds=3):
                    logger.warning("未找到联系人列表控件，尝试备用方案...")
                    return self._get_friends_by_search()

            # 滚动获取所有好友
            max_scroll_attempts = 200
            no_new_count = 0
            max_no_new = 10

            for _ in range(max_scroll_attempts):
                items = contact_list.GetChildren()
                new_found = False

                for item in items:
                    name = item.Name.strip()
                    if name and name not in seen:
                        seen.add(name)
                        friends.append(name)
                        new_found = True

                if new_found:
                    no_new_count = 0
                    logger.info("  已获取 %d 个联系人...", len(friends))
                else:
                    no_new_count += 1

                if no_new_count >= max_no_new:
                    logger.info("已到达列表末尾")
                    break

                contact_list.WheelDown(wheelTimes=3)
                time.sleep(0.3)

            logger.info("✅ 共获取 %d 个联系人", len(friends))
            return friends

        except Exception as e:
            logger.error("获取好友列表失败: %s", e)
            return friends if friends else []

    def _get_friends_by_search(self) -> List[str]:
        """
        备用方案：通过搜索框逐字母搜索获取好友。
        当无法直接访问通讯录列表时使用。
        """
        logger.info("使用搜索方式获取好友列表...")
        friends: List[str] = []
        seen: Set[str] = set()

        search_chars = list('abcdefghijklmnopqrstuvwxyz0123456789')

        for char in search_chars:
            try:
                results = self._search_and_collect(char)
                for name in results:
                    if name not in seen:
                        seen.add(name)
                        friends.append(name)
                time.sleep(0.3)
            except Exception as e:
                logger.warning("搜索 '%s' 时出错: %s", char, e)
                continue

        logger.info("✅ 通过搜索获取 %d 个好友", len(friends))
        return friends

    def _search_and_collect(self, keyword: str) -> List[str]:
        """在搜索框中搜索并收集结果"""
        results: List[str] = []
        if not self.wechat_window:
            return results

        try:
            search_box = self.wechat_window.EditControl(Name='搜索')
            if not search_box.Exists(maxSearchSeconds=2):
                auto.SendKeys('{Ctrl}f')
                time.sleep(0.5)
                search_box = self.wechat_window.EditControl(Name='搜索')

            if search_box.Exists(maxSearchSeconds=2):
                search_box.Click()
                time.sleep(0.2)
                search_box.SendKeys(keyword, waitTime=0)
                time.sleep(1)

                search_result = self.wechat_window.ListControl(Name='搜索结果')
                if search_result.Exists(maxSearchSeconds=2):
                    items = search_result.GetChildren()
                    for item in items:
                        name = item.Name.strip()
                        if name:
                            results.append(name)

                search_box.SendKeys('{Ctrl}a{Delete}', waitTime=0)
                time.sleep(0.3)
                auto.SendKeys('{Escape}')
                time.sleep(0.3)

        except Exception as e:
            logger.debug("搜索 '%s' 失败: %s", keyword, e)
            try:
                auto.SendKeys('{Escape}')
                time.sleep(0.2)
            except Exception:
                pass

        return results

    def search_and_open_chat(self, friend_name: str) -> bool:
        """
        搜索好友并打开聊天窗口。

        Args:
            friend_name: 好友名称

        Returns:
            是否成功打开聊天窗口
        """
        if not self.wechat_window:
            return False

        try:
            self.wechat_window.SetActive()
            time.sleep(0.2)

            # 使用 Ctrl+F 打开搜索
            auto.SendKeys('{Ctrl}f')
            time.sleep(0.8)

            # 使用剪贴板粘贴好友名称（支持中文）
            pyperclip.copy(friend_name)
            time.sleep(0.1)
            auto.SendKeys('{Ctrl}a')
            time.sleep(0.1)
            auto.SendKeys('{Ctrl}v')
            time.sleep(1.2)

            # 按回车选择第一个搜索结果
            auto.SendKeys('{Enter}')
            time.sleep(1.0)

            logger.debug("已打开与 %s 的聊天窗口", friend_name)
            return True

        except Exception as e:
            logger.error("搜索好友 %s 失败: %s", friend_name, e)
            try:
                auto.SendKeys('{Escape}')
                time.sleep(0.3)
            except Exception:
                pass
            return False

    def send_message_to_current_chat(self, message: str) -> bool:
        """
        在当前聊天窗口发送消息。

        Args:
            message: 要发送的消息

        Returns:
            是否发送成功
        """
        if not self.wechat_window:
            return False

        try:
            self.wechat_window.SetActive()
            time.sleep(0.2)

            # 查找消息输入框
            edit_box = self.wechat_window.EditControl(Name='输入')
            if edit_box.Exists(maxSearchSeconds=2):
                edit_box.Click()
                time.sleep(0.2)

            # 使用剪贴板粘贴消息
            pyperclip.copy(message)
            time.sleep(0.1)
            auto.SendKeys('{Ctrl}v')
            time.sleep(0.3)

            # 发送消息
            auto.SendKeys('{Enter}')
            time.sleep(0.5)

            return True

        except Exception as e:
            logger.error("发送消息失败: %s", e)
            return False

    def send_blessing_to_friend(self, friend_name: str, message: str) -> bool:
        """
        向指定好友发送祝福消息。

        Args:
            friend_name: 好友名称
            message: 祝福消息

        Returns:
            是否发送成功
        """
        if not self.search_and_open_chat(friend_name):
            return False
        return self.send_message_to_current_chat(message)


    def inspect_wechat_ui(self) -> dict:
        """
        探测微信 UI 控件结构，输出所有控件信息
        用于适配不同版本的微信

        Returns:
            控件信息字典
        """
        if not self.wechat_window:
            if not self.find_wechat():
                return {}

        self.wechat_window.SetActive()
        time.sleep(0.5)

        result = {
            'window': {
                'Name': self.wechat_window.Name,
                'ClassName': self.wechat_window.ClassName,
                'Rect': str(self.wechat_window.BoundingRectangle),
            },
            'buttons': [],
            'lists': [],
            'edit_boxes': [],
            'all_children': [],
        }

        # 探测所有按钮
        try:
            buttons = self.wechat_window.GetChildren()
            for btn in buttons:
                if hasattr(btn, 'ControlTypeName'):
                    result['buttons'].append({
                        'Name': btn.Name,
                        'ClassName': btn.ClassName,
                        'ControlType': btn.ControlTypeName,
                    })
        except Exception as e:
            logger.debug("探测按钮失败: %s", e)

        # 探测所有列表控件
        try:
            lists = self.wechat_window.GetDescendants()
            for lst in lists:
                if hasattr(lst, 'ControlTypeName') and 'List' in lst.ControlTypeName:
                    result['lists'].append({
                        'Name': lst.Name,
                        'ClassName': lst.ClassName,
                        'ControlType': lst.ControlTypeName,
                        'Rect': str(lst.BoundingRectangle),
                    })
        except Exception as e:
            logger.debug("探测列表失败: %s", e)

        # 探测所有编辑框
        try:
            edits = self.wechat_window.GetDescendants()
            for edit in edits:
                if hasattr(edit, 'ControlTypeName') and 'Edit' in edit.ControlTypeName:
                    result['edit_boxes'].append({
                        'Name': edit.Name,
                        'ClassName': edit.ClassName,
                        'ControlType': edit.ControlTypeName,
                    })
        except Exception as e:
            logger.debug("探测编辑框失败: %s", e)

        # 探测所有子控件（深度1）
        try:
            children = self.wechat_window.GetChildren()
            for i, child in enumerate(children[:50]):  # 限制输出数量
                result['all_children'].append({
                    'Index': i,
                    'Name': child.Name,
                    'ClassName': child.ClassName,
                    'ControlType': child.ControlTypeName if hasattr(child, 'ControlTypeName') else 'Unknown',
                })
        except Exception as e:
            logger.debug("探测子控件失败: %s", e)

        return result


# ─── 祝福发送管理器 ────────────────────────────────────────────────────────

class BlessingManager:
    """祝福发送管理器：负责好友列表管理、祝福语分配、进度跟踪"""

    def __init__(self):
        self.blessings: List[str] = []
        self.friends: List[str] = []
        self.exclude_set: Set[str] = set()
        self.exclude_keywords: List[str] = list(DEFAULT_EXCLUDE_KEYWORDS)
        self.progress: Dict = {}
        self.used_blessings: Set[str] = set()

        self._load_all()

    def _load_all(self):
        """加载所有配置和数据"""
        self._load_blessings()
        self._load_friends()
        self._load_exclude_list()
        self._load_progress()

    def _load_blessings(self):
        """加载祝福语"""
        self.blessings = load_text_lines(BLESSINGS_FILE)
        if not self.blessings:
            logger.error("❌ 祝福语文件 %s 为空或不存在", BLESSINGS_FILE)
            sys.exit(1)
        logger.info("📝 已加载 %d 条祝福语", len(self.blessings))

    def _load_friends(self):
        """加载好友列表"""
        self.friends = load_text_lines(FRIENDS_FILE)
        if self.friends:
            logger.info("👥 已加载 %d 个好友", len(self.friends))
        else:
            logger.info("👥 好友列表为空，需要先获取好友")

    def _load_exclude_list(self):
        """加载排除列表"""
        custom_excludes = load_text_lines(EXCLUDE_FILE)
        self.exclude_set = set(custom_excludes)
        for kw in self.exclude_keywords:
            self.exclude_set.add(kw)
        logger.info("🚫 排除列表: %d 项", len(self.exclude_set))

    def _load_progress(self):
        """加载发送进度"""
        self.progress = load_json(PROGRESS_FILE)
        if self.progress:
            sent = self.progress.get('sent', [])
            logger.info("📊 已有发送记录: %d 个好友已发送", len(sent))
            for entry in sent:
                blessing = entry.get('blessing', '')
                if blessing:
                    self.used_blessings.add(blessing)

    def save_progress(self):
        """保存发送进度"""
        save_json(PROGRESS_FILE, self.progress)

    def is_excluded(self, name: str) -> bool:
        """检查好友是否在排除列表中"""
        if name in self.exclude_set:
            return True
        for kw in self.exclude_keywords:
            if kw in name:
                return True
        return False

    def get_sendable_friends(self) -> List[str]:
        """获取可发送的好友列表（排除已发送和排除列表中的）"""
        sent_names: Set[str] = set()
        if self.progress.get('sent'):
            sent_names = {entry['name'] for entry in self.progress['sent']}

        sendable = []
        for friend in self.friends:
            if friend not in sent_names and not self.is_excluded(friend):
                sendable.append(friend)
        return sendable

    def get_random_blessing(self) -> str:
        """获取随机不重复的祝福语"""
        available = [b for b in self.blessings if b not in self.used_blessings]
        if not available:
            logger.info("所有祝福语已使用过，重置使用记录")
            self.used_blessings.clear()
            available = list(self.blessings)

        blessing = random.choice(available)
        self.used_blessings.add(blessing)
        return blessing

    def record_sent(self, friend_name: str, blessing: str, success: bool):
        """记录发送结果"""
        if 'sent' not in self.progress:
            self.progress['sent'] = []
        if 'failed' not in self.progress:
            self.progress['failed'] = []

        entry = {
            'name': friend_name,
            'blessing': blessing,
            'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'success': success,
        }

        if success:
            self.progress['sent'].append(entry)
        else:
            self.progress['failed'].append(entry)

        self.progress['last_update'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.save_progress()

    def update_friends(self, new_friends: List[str]):
        """更新好友列表（去重 + 过滤排除项）"""
        existing = set(self.friends)
        added = 0
        for friend in new_friends:
            if friend and friend not in existing and not self.is_excluded(friend):
                self.friends.append(friend)
                existing.add(friend)
                added += 1

        save_text_lines(FRIENDS_FILE, self.friends)
        logger.info("✅ 好友列表已更新: 新增 %d 个，总计 %d 个", added, len(self.friends))

    def reset_progress(self):
        """重置发送进度"""
        self.progress = {}
        self.used_blessings.clear()
        if os.path.exists(PROGRESS_FILE):
            os.remove(PROGRESS_FILE)
        logger.info("✅ 发送进度已重置")

    def show_status(self):
        """显示当前发送状态"""
        total = len(self.friends)
        sent_count = len(self.progress.get('sent', []))
        failed_count = len(self.progress.get('failed', []))
        sendable = self.get_sendable_friends()

        print("\n" + "=" * 60)
        print("        📊 新年祝福发送状态")
        print("=" * 60)
        print(f"  好友总数:     {total}")
        print(f"  已发送:       {sent_count}")
        print(f"  发送失败:     {failed_count}")
        print(f"  待发送:       {len(sendable)}")
        print(f"  排除列表:     {len(self.exclude_set)} 项")
        print(f"  祝福语总数:   {len(self.blessings)} 条")

        if self.progress.get('last_update'):
            print(f"  最后更新:     {self.progress['last_update']}")

        if self.progress.get('failed'):
            print("\n  ⚠️ 发送失败的好友:")
            for entry in self.progress['failed']:
                print(f"    - {entry['name']} ({entry['time']})")

        print("=" * 60 + "\n")


# ─── 主控制器 ──────────────────────────────────────────────────────────────

class AutoBlessingController:
    """全自动祝福发送控制器"""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.wechat = WeChatAutomation()
        self.manager = BlessingManager()

        # 发送间隔（秒）：随机化以避免被检测
        self.min_interval = 2.0
        self.max_interval = 5.0

    def fetch_friends(self) -> bool:
        """自动获取微信好友列表"""
        logger.info("🔄 开始自动获取微信好友列表...")

        if not self.wechat.find_wechat():
            return False

        self.wechat.switch_to_contacts()
        time.sleep(1)

        friends = self.wechat.get_all_friends_from_contacts()

        if not friends:
            logger.warning("⚠️ 未获取到好友，请检查微信是否已打开通讯录")
            return False

        self.manager.update_friends(friends)
        return True

    def send_to_all(self, resume: bool = False) -> bool:
        """
        向所有好友发送祝福。

        Args:
            resume: 是否断点续发
        """
        sendable = self.manager.get_sendable_friends()

        if not sendable:
            if resume:
                logger.info("✅ 所有好友都已发送过祝福！")
            else:
                logger.error("❌ 没有可发送的好友，请先获取好友列表")
            return False

        total = len(sendable)
        logger.info("")
        logger.info("=" * 60)
        logger.info("  🎊 准备向 %d 个好友发送新年祝福", total)
        if self.dry_run:
            logger.info("  ⚠️ 模拟运行模式（不会实际发送）")
        logger.info("=" * 60)
        logger.info("")

        if not self.dry_run:
            if not self.wechat.find_wechat():
                return False

            logger.info("⏳ 5秒后开始发送，请勿操作电脑...")
            for i in range(5, 0, -1):
                logger.info("  %d...", i)
                time.sleep(1)

        success_count = 0
        fail_count = 0

        try:
            for idx, friend_name in enumerate(sendable, 1):
                blessing = self.manager.get_random_blessing()

                logger.info("")
                logger.info("[%d/%d] 👤 %s", idx, total, friend_name)
                preview = blessing[:50] + ('...' if len(blessing) > 50 else '')
                logger.info("  💬 %s", preview)

                if self.dry_run:
                    logger.info("  ✅ [模拟] 发送成功")
                    self.manager.record_sent(friend_name, blessing, True)
                    success_count += 1
                else:
                    success = self.wechat.send_blessing_to_friend(friend_name, blessing)

                    if success:
                        logger.info("  ✅ 发送成功")
                        self.manager.record_sent(friend_name, blessing, True)
                        success_count += 1
                    else:
                        logger.warning("  ❌ 发送失败")
                        self.manager.record_sent(friend_name, blessing, False)
                        fail_count += 1

                # 随机间隔
                if idx < total:
                    interval = random.uniform(self.min_interval, self.max_interval)
                    logger.debug("  ⏳ 等待 %.1f 秒...", interval)
                    time.sleep(interval)

        except KeyboardInterrupt:
            logger.info("\n\n⚠️ 用户中断发送")
            logger.info("  已发送: %d/%d", success_count, total)
            logger.info("  失败: %d", fail_count)
            logger.info("  剩余: %d", total - success_count - fail_count)
            logger.info("\n💡 使用 --resume 参数可以继续发送剩余好友")
            self.manager.save_progress()
            return False

        # 发送完成统计
        logger.info("")
        logger.info("=" * 60)
        logger.info("  🎉 发送完成！")
        logger.info("  ✅ 成功: %d/%d", success_count, total)
        logger.info("  ❌ 失败: %d", fail_count)
        logger.info("=" * 60)
        logger.info("")

        return True

    def run_full_auto(self):
        """全自动流程：获取好友 → 发送祝福"""
        logger.info("🚀 启动全自动新年祝福发送...")
        logger.info("  当前时间: %s", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

        # 第一步：获取好友列表
        if not self.manager.friends:
            logger.info("\n📋 第一步：获取好友列表")
            if not self.fetch_friends():
                logger.error("获取好友列表失败，退出")
                return
        else:
            logger.info("\n📋 已有好友列表: %d 个好友", len(self.manager.friends))
            sendable = self.manager.get_sendable_friends()
            if not sendable:
                logger.info("所有好友都已发送过祝福！")
                logger.info("如需重新发送，请使用 --reset 重置进度后重试")
                return
            logger.info("  待发送: %d 个好友", len(sendable))

        # 第二步：发送祝福
        logger.info("\n🎊 第二步：发送新年祝福")
        self.send_to_all(resume=True)


# ─── 初始化排除列表文件 ────────────────────────────────────────────────────

def init_exclude_file():
    """如果排除列表文件不存在，创建默认的"""
    if not os.path.exists(EXCLUDE_FILE):
        with open(EXCLUDE_FILE, 'w', encoding='utf-8') as f:
            f.write("# 排除列表：每行一个名称，这些好友不会收到祝福\n")
            f.write("# 以 # 开头的行为注释\n")
            f.write("\n".join(DEFAULT_EXCLUDE_KEYWORDS) + "\n")
        logger.info("✅ 已创建默认排除列表: %s", EXCLUDE_FILE)


# ─── 命令行入口 ────────────────────────────────────────────────────────────

def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='微信新年祝福全自动发送脚本',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python auto_blessing_full.py              # 全自动：获取好友 + 发送祝福
  python auto_blessing_full.py --fetch      # 仅获取好友列表
  python auto_blessing_full.py --send       # 仅发送祝福
  python auto_blessing_full.py --resume     # 断点续发
  python auto_blessing_full.py --status     # 查看发送进度
  python auto_blessing_full.py --dry-run    # 模拟运行
  python auto_blessing_full.py --reset      # 重置发送进度
  python auto_blessing_full.py --inspect    # 探测微信UI控件结构
        """
    )
    parser.add_argument('--fetch', action='store_true',
                        help='仅获取好友列表')
    parser.add_argument('--send', action='store_true',
                        help='仅发送祝福（使用已有好友列表）')
    parser.add_argument('--resume', action='store_true',
                        help='断点续发（跳过已发送的好友）')
    parser.add_argument('--status', action='store_true',
                        help='查看发送进度')
    parser.add_argument('--dry-run', action='store_true',
                        help='模拟运行（不实际发送）')
    parser.add_argument('--reset', action='store_true',
                        help='重置发送进度')
    parser.add_argument('--inspect', action='store_true',
                        help='探测微信UI控件结构（用于适配不同版本）')
    return parser.parse_args()


def main():
    """主函数"""
    args = parse_args()

    # 初始化排除列表文件
    init_exclude_file()

    # 检查祝福语文件
    if not os.path.exists(BLESSINGS_FILE):
        print(f"❌ 找不到祝福语文件 {BLESSINGS_FILE}")
        print("请确保该文件与脚本在同一目录下")
        sys.exit(1)

    # 查看状态
    if args.status:
        manager = BlessingManager()
        manager.show_status()
        return

    # 重置进度
    if args.reset:
        manager = BlessingManager()
        manager.reset_progress()
        return

    # 探测微信UI
    if args.inspect:
        print("\n" + "=" * 60)
        print("        🔍 微信 UI 控件探测")
        print("=" * 60)
        wechat = WeChatAutomation()
        result = wechat.inspect_wechat_ui()
        if result:
            print("\n【窗口信息】")
            for k, v in result.get('window', {}).items():
                print(f"  {k}: {v}")

            print("\n【列表控件】")
            for lst in result.get('lists', []):
                print(f"  Name: {lst.get('Name', 'N/A')}")
                print(f"    ClassName: {lst.get('ClassName', 'N/A')}")
                print(f"    ControlType: {lst.get('ControlType', 'N/A')}")
                print(f"    Rect: {lst.get('Rect', 'N/A')}")

            print("\n【编辑框控件】")
            for edit in result.get('edit_boxes', []):
                print(f"  Name: {edit.get('Name', 'N/A')}")
                print(f"    ClassName: {edit.get('ClassName', 'N/A')}")
                print(f"    ControlType: {edit.get('ControlType', 'N/A')}")

            print("\n【按钮控件（前20个）】")
            for btn in result.get('buttons', [])[:20]:
                print(f"  Name: {btn.get('Name', 'N/A')}")
                print(f"    ClassName: {btn.get('ClassName', 'N/A')}")
                print(f"    ControlType: {btn.get('ControlType', 'N/A')}")

            print("\n【所有子控件（前50个）】")
            for child in result.get('all_children', []):
                print(f"  [{child.get('Index', '?')}] Name: {child.get('Name', 'N/A')}")
                print(f"      ClassName: {child.get('ClassName', 'N/A')}")
                print(f"      ControlType: {child.get('ControlType', 'N/A')}")

            print("\n" + "=" * 60)
            print("💡 提示：")
            print("  - 请记下'通讯录'按钮的 Name 和 ClassName")
            print("  - 请记下'联系人'列表的 Name 和 ClassName")
            print("  - 请记下'搜索'编辑框的 Name 和 ClassName")
            print("  - 如控件名称与代码中不同，请告知以便更新")
            print("=" * 60 + "\n")
        return

    # 创建控制器
    dry_run = getattr(args, 'dry_run', False)
    controller = AutoBlessingController(dry_run=dry_run)

    if args.fetch:
        # 仅获取好友列表
        controller.fetch_friends()
    elif args.send:
        # 仅发送祝福
        controller.send_to_all(resume=False)
    elif args.resume:
        # 断点续发
        controller.send_to_all(resume=True)
    else:
        # 全自动模式
        controller.run_full_auto()


if __name__ == '__main__':
    main()