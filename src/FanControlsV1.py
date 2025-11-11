import json
import time
import sys
import clr
import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import logging
from logging.handlers import RotatingFileHandler
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from datetime import datetime
from tkinter import PhotoImage

plt.rcParams['font.sans-serif'] = ["SimHei"]  # 设置字体为黑体
plt.rcParams['axes.unicode_minus'] = False  # 正常显示负号


def get_resource_path(relative_path):
    """获取资源文件的正确路径（兼容开发环境和打包后环境）"""
    if hasattr(sys, '_MEIPASS'):
        # 打包后：资源位于 PyInstaller 临时目录
        return os.path.join(sys._MEIPASS, relative_path)
    # 开发时：资源位于当前脚本所在目录的相对路径
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(current_dir, relative_path)


# 加载 DLL（假设 Central.iGame.dll 在开发环境中与当前脚本同目录，或按实际相对路径调整）
dll_path = get_resource_path("bin/Central.iGame.dll")  # 如果 DLL 在 bin 目录下，这里改为 "bin/Central.iGame.dll"
clr.AddReference(dll_path)
from Central import Wmi


def get_file_path(relative_path):
    """获取配置文件路径（外部可编辑）"""
    if hasattr(sys, '_MEIPASS'):
        # 打包后：可执行文件所在目录（不是临时目录）
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        return os.path.join(exe_dir, relative_path)
    else:
        # 开发时：项目源码目录（根据实际结构调整）
        project_dir = os.path.dirname(os.path.abspath(__file__))  # 当前脚本所在目录
        return os.path.join(project_dir, "data", relative_path)  # 配置文件在 ./data 下


class FanController:
    """风扇    风扇控制核心类，负责与硬件交互和控制逻辑处理
    包括性能模式切换、风扇模式控制、温度/转速获取等核心功能
    """

    def __init__(self):
        # 核心参数初始化
        self.wmi = Wmi  # 硬件交互类（静态方法调用）
        self.monitor_interval = 1  # 监控间隔（秒）
        self.low_temp_threshold = 45  # 低温阈值（℃）
        self.current_fan_mode = "auto"  # 当前风扇模式（auto/manual）
        self.speed_conversion = 63  # 百分比转原始值系数（0-100% → 0-6300）
        self.current_perf_mode = "未知"  # 当前系统性能模式
        self.applied_cpu_curve = {}  # 应用中的CPU风扇曲线
        self.applied_gpu_curve = {}  # 应用中的GPU风扇曲线
        self.is_custom_mode = False  # 是否启用自定义模式
        self.is_full_mode = False  # 是否启用强冷模式
        self.last_non_full_mode = "auto"  # 强冷启用前的模式（用于恢复）

        # 性能模式映射（code: name）
        self.perf_mode_map = {
            2: "狂暴模式",
            1: "静音游戏",
            0: "超长续航",
        }
        # 反向映射（name: code）
        self.perf_mode_code = {v: k for k, v in self.perf_mode_map.items()}

        # 初始化硬件状态
        self.wmi.SetFanFullMode(False)  # 初始关闭强冷
        self.wmi.FanControlOpen(False)  # 初始为自动模式
        self._load_default_config()  # 加载默认曲线配置
        self.load_config()

        # 初始化强冷模式状态检测
        try:
            full_mode_status = self.wmi.GetFanFullMode()
            self.is_full_mode = full_mode_status != 0
            logging.info(f"初始强冷模式状态: {'已启用' if self.is_full_mode else '已禁用'}")
        except Exception as e:
            logging.error(f"获取强冷模式状态失败: {str(e)}")

    def _load_default_config(self):
        """加载默认风扇曲线配置（0-90度，每10度一个控制点）"""
        # 默认CPU风扇曲线（0-90度对应的转速百分比）
        self.cpu_fans = [0, 38, 38, 38, 38, 47, 55, 64, 74, 83]
        # 默认GPU风扇曲线（0-90度对应的转速百分比）
        self.gpu_fans = [0, 38, 38, 38, 38, 47, 55, 64, 74, 83]

        # 转换为温度-转速字典（10度间隔：0,10,20,...,90）
        self.applied_cpu_curve = {i * 10: self.cpu_fans[i] for i in range(10)}
        self.applied_gpu_curve = {i * 10: self.gpu_fans[i] for i in range(10)}

    def save_config(self, file_path=None):
        """保存配置到JSON文件（包含模式状态和曲线参数）"""
        if not file_path:
            file_path = get_file_path("fan_config.json")

        # 构建配置字典
        config = {
            "CpuFans": self.cpu_fans,
            "GpuFans": self.gpu_fans,
            "LowTempThreshold": self.low_temp_threshold,
            "CurrentFanMode": self.current_fan_mode,
            "IsCustomMode": self.is_custom_mode,
            "IsFullMode": self.is_full_mode,
            "LastNonFullMode": self.last_non_full_mode
        }

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=4)
            return True, file_path
        except Exception as e:
            return False, str(e)

    def load_config(self, file_path=None):
        """从JSON文件加载配置（恢复模式状态和曲线参数）"""
        if not file_path:
            file_path = get_file_path("fan_config.json")

        if not os.path.exists(file_path):
            return False, "配置文件不存在"

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                config = json.load(f)

            # 加载风扇曲线（确保长度正确）
            self.cpu_fans = config.get("CpuFans", [0, 38, 38, 38, 38, 47, 55, 64, 74, 83])
            self.gpu_fans = config.get("GpuFans", [0, 38, 38, 38, 38, 47, 55, 64, 74, 83])
            if len(self.cpu_fans) != 10:
                self.cpu_fans = [0, 38, 38, 38, 38, 47, 55, 64, 74, 83]
            if len(self.gpu_fans) != 10:
                self.gpu_fans = [0, 38, 38, 38, 38, 47, 55, 64, 74, 83]

            # 加载模式状态和阈值
            self.low_temp_threshold = config.get("LowTempThreshold", 45)
            self.current_fan_mode = config.get("CurrentFanMode", "auto")
            self.is_custom_mode = config.get("IsCustomMode", False)
            self.is_full_mode = config.get("IsFullMode", False)
            self.last_non_full_mode = config.get("LastNonFullMode", "auto")

            # 转换为温度-转速字典
            self.applied_cpu_curve = {i * 10: self.cpu_fans[i] for i in range(10)}
            self.applied_gpu_curve = {i * 10: self.gpu_fans[i] for i in range(10)}

            # 同步硬件状态
            if self.is_full_mode:
                self.wmi.SetFanFullMode(True)
                self.wmi.FanControlOpen(False)
            else:
                self.wmi.SetFanFullMode(False)
                self.wmi.FanControlOpen(self.is_custom_mode)

            return True, file_path
        except Exception as e:
            return False, str(e)

    def query_current_mode(self):
        """查询当前系统性能模式"""
        try:
            mode_code = self.wmi.GetPerformanceMode()
            self.current_perf_mode = self.perf_mode_map.get(mode_code, f"未知模式({mode_code})")
            return self.current_perf_mode, mode_code
        except Exception as e:
            raise Exception(f"查询当前模式失败：{str(e)}")

    def set_system_perf_mode(self, mode_name):
        """切换系统性能模式"""
        try:
            mode_code = self.perf_mode_code[mode_name]
            result = self.wmi.SetPerformanceMode(mode_code)
            return result
        except Exception as e:
            raise Exception(f"切换{mode_name}失败：{str(e)}")

    def switch_fan_mode(self, mode_code):
        """切换基础风扇模式（auto/manual）"""
        try:
            # 切换模式时自动关闭强冷
            if self.is_full_mode:
                self.wmi.SetFanFullMode(False)
                self.is_full_mode = False

            # 更新模式状态
            if mode_code == "auto":
                self.wmi.FanControlOpen(False)
                self.is_custom_mode = False
                self.current_fan_mode = "auto"
                self.last_non_full_mode = "auto"
            elif mode_code == "manual":
                self.wmi.FanControlOpen(True)
                self.is_custom_mode = True
                self.current_fan_mode = "manual"
                self.last_non_full_mode = "manual"
            else:
                raise ValueError(f"无效模式：{mode_code}（必须是 'auto' 或 'manual'）")

            self.save_config()  # 保存状态
        except Exception as e:
            logging.error(f"切换风扇模式失败: {str(e)}")
            raise

    def toggle_full_mode(self, enable):
        """切换强冷模式（开/关）"""
        try:
            if enable:
                # 启用强冷：记录当前模式并关闭自定义
                self.last_non_full_mode = self.current_fan_mode
                self.wmi.SetFanFullMode(True)
                self.wmi.FanControlOpen(False)
                self.is_full_mode = True
                self.is_custom_mode = False
            else:
                # 禁用强冷：恢复到之前的模式
                self.wmi.SetFanFullMode(False)
                self.is_full_mode = False
                self.current_fan_mode = self.last_non_full_mode
                if self.current_fan_mode == "manual":
                    self.wmi.FanControlOpen(True)
                    self.is_custom_mode = True
                else:
                    self.wmi.FanControlOpen(False)
                    self.is_custom_mode = False

            self.save_config()  # 保存状态
            logging.info(f"强冷模式已{'启用' if enable else '禁用'}")
            return True
        except Exception as e:
            logging.error(f"切换强冷模式失败: {str(e)}")
            raise

    def get_temperatures(self):
        """获取CPU和GPU温度（℃）"""
        try:
            return {
                "cpu": round(float(self.wmi.GetCPUTem()), 1),
                "gpu": round(float(self.wmi.GetGPUTem()), 1)
            }
        except Exception as e:
            raise Exception(f"获取温度失败：{str(e)}")

    def get_fan_speeds(self):
        """获取CPU和GPU风扇转速（转/分）"""
        try:
            return {
                "cpu": self.wmi.GetCpufanSpeed(),
                "gpu": self.wmi.GetGpufanSpeed()
            }
        except Exception as e:
            raise Exception(f"获取风扇转速失败：{str(e)}")

    def calculate_speed(self, temp, curve):
        """
        根据温度和曲线计算目标转速（原始值）
        优化点：
        1. 预缓存排序后的温度列表（避免重复排序）
        2. 用二分查找替代线性遍历（提升中间温度查找效率）
        3. 优化边界条件处理（确保极端温度的稳定性）
        """
        # 预排序温度点（仅在首次调用时排序，后续直接使用缓存）
        if not hasattr(self, '_sorted_temps_cache') or self._sorted_temps_cache.get(id(curve)) is None:
            sorted_temps = sorted(curve.keys())
            self._sorted_temps_cache = {id(curve): sorted_temps}  # 用曲线对象ID作为缓存键
        else:
            sorted_temps = self._sorted_temps_cache[id(curve)]

        min_temp = sorted_temps[0]
        max_temp = sorted_temps[-1]

        # 边界处理：低于最低温度点
        if temp <= min_temp:
            return int(curve[min_temp] * self.speed_conversion)
        # 边界处理：高于最高温度点
        if temp >= max_temp:
            return int(curve[max_temp] * self.speed_conversion)

        # 二分查找找到温度所在的区间（替代线性遍历，适合大量控制点场景）
        left, right = 0, len(sorted_temps) - 1
        while left < right:
            mid = (left + right) // 2
            if sorted_temps[mid] < temp:
                left = mid + 1
            else:
                right = mid
        # 确定区间 [t1, t2]
        t2_idx = left
        t1_idx = t2_idx - 1
        t1, t2 = sorted_temps[t1_idx], sorted_temps[t2_idx]
        s1, s2 = curve[t1], curve[t2]

        # 线性插值计算转速（保持平滑过渡）
        ratio = (temp - t1) / (t2 - t1)
        target_speed = s1 + (s2 - s1) * ratio
        # 转换为原始值并取整（确保转速为整数，避免硬件异常）
        return int(round(target_speed * self.speed_conversion))

    def set_fan_speed(self, cpu_speed, gpu_speed):
        """设置风扇转速（原始值）"""
        try:
            # 限制转速范围（0-6300）
            cpu_clamped = max(0, min(6300, cpu_speed))
            gpu_clamped = max(0, min(6300, gpu_speed))
            self.wmi.SetFanSpeed(cpu_clamped, gpu_clamped)
            return True
        except Exception as e:
            raise Exception(f"设置风扇转速失败：{str(e)}")

    def custom_fan_control(self, temps):
        """自定义模式下的风扇控制逻辑"""
        if self.is_full_mode:
            return "当前为强冷模式（全速运行）", False

        cpu_temp, gpu_temp = temps["cpu"], temps["gpu"]
        is_low_temp = (cpu_temp < self.low_temp_threshold) and (gpu_temp < self.low_temp_threshold)
        log_msg = ""
        mode_changed = False

        # 低温时自动切换到自动模式
        if is_low_temp:
            if self.current_fan_mode != "auto":
                self.wmi.FanControlOpen(False)
                self.current_fan_mode = "auto"
                self.is_custom_mode = False
                self.last_non_full_mode = "auto"
                mode_changed = True
                log_msg = f"切换至自动风扇（双温低于{self.low_temp_threshold}℃）"
        # 高温时使用自定义曲线
        else:
            if self.current_fan_mode != "manual":
                self.wmi.FanControlOpen(True)
                self.current_fan_mode = "manual"
                self.is_custom_mode = True
                self.last_non_full_mode = "manual"
                mode_changed = True
                log_msg = f"切换至自定义风扇（温度≥{self.low_temp_threshold}℃）"

            # 计算并设置目标转速
            cpu_target = self.calculate_speed(cpu_temp, self.applied_cpu_curve)
            gpu_target = self.calculate_speed(gpu_temp, self.applied_gpu_curve)
            self.set_fan_speed(cpu_target, gpu_target)

            if not log_msg:
                log_msg = f"CPU目标: {cpu_target}转 | GPU目标: {gpu_target}转"

        return log_msg, mode_changed

    def restore_default_mode(self):
        """程序退出时恢复默认风扇模式"""
        try:
            self.wmi.FanControlOpen(False)  # 关闭自定义
            self.wmi.SetFanFullMode(False)  # 关闭强冷
            self.current_fan_mode = "auto"
            self.is_custom_mode = False
            self.is_full_mode = False
        except Exception as e:
            logging.warning(f"恢复默认模式失败: {str(e)}")


class FanCurveGUI:
    """
    风扇控制GUI界面类，负责用户交互和状态显示
    包括实时监控、模式切换、曲线配置和日志查看等功能
    """

    def __init__(self, root, controller, logger):
        self.root = root
        self.controller = controller
        self.logger = logger
        self.is_monitoring = False  # 监控状态标记
        self.log_window = None  # 日志窗口引用
        self.log_refresh_active = False  # 日志刷新状态

        # 模式映射（UI显示文本 → 内部模式代码）
        self.fan_mode_mapping = {
            "自动模式": "auto",
            "自定义模式": "manual"
        }
        self.reverse_fan_mapping = {v: k for k, v in self.fan_mode_mapping.items()}

        # 状态记录（用于检测变化）
        self.last_perf_mode = ""
        self.last_fan_mode = ""

        # 界面样式配置
        self.style = ttk.Style()
        self.style.configure("Header.TLabel", font=("微软雅黑", 20, "bold"))
        self.style.configure("Status.TLabel", font=("微软雅黑", 18))
        self.style.configure("Accent.TButton", foreground="#e74c3c", font=("微软雅黑", 16, "bold"))
        self.style.configure("TLabelframe.Label", font=("微软雅黑", 18))
        self.style.configure("Custom.TRadiobutton", font=('SimHei', 16))
        self.style.configure("Custom.TButton", font=('SimHei', 16))

        # 实时状态变量
        self.current_cpu_temp = tk.StringVar(value="--℃")
        self.current_gpu_temp = tk.StringVar(value="--℃")
        self.current_cpu_speed = tk.StringVar(value="--转")
        self.current_gpu_speed = tk.StringVar(value="--转")
        self.current_status = tk.StringVar(value="初始化中...")

        # 模式选择变量
        self.fan_mode_var = tk.StringVar(value="自动模式")
        self.full_mode_choice = tk.StringVar(  # 强冷模式选项（开/关）
            value="开" if self.controller.is_full_mode else "关"
        )

        # 曲线编辑缓存
        self.edit_cpu_curve = self.controller.applied_cpu_curve.copy()
        self.edit_gpu_curve = self.controller.applied_gpu_curve.copy()

        # 初始化界面
        self.root.title("iGame风扇控制")
        self.root.geometry("1400x800")
        self.root.minsize(1200, 800)
        self.root.resizable(True, True)

        # 创建界面组件
        self._create_widgets()
        self._init_plot()  # 初始化曲线图

        # 启动初始化
        try:
            self._query_current_mode()
            self._update_plot()
            self.start_monitoring()

            # 初始化模式选择状态
            self.fan_mode_var.set("自定义模式")
            self.full_mode_choice.set("关")
            self.switch_fan_mode()

            # 更新初始状态
            self.update_status_text()
            self.last_perf_mode = controller.current_perf_mode
            self.last_fan_mode = self._get_current_fan_mode_text()
            self.logger.info("系统初始化完成")
        except Exception as e:
            error_msg = f"初始化错误：{str(e)}"
            self.logger.error(error_msg)
            messagebox.showerror("初始化失败", error_msg)
            self.root.destroy()

    def _create_widgets(self):
        """创建界面组件"""
        # 主容器
        main_container = ttk.Frame(self.root, padding="10 10 10 10")
        main_container.pack(fill="both", expand=True)

        # 顶部状态监控卡片
        status_card = ttk.LabelFrame(main_container, text="实时状态监控", padding="10 10 10 10")
        status_card.pack(fill="x", pady=(0, 10))

        status_grid = ttk.Frame(status_card)
        status_grid.pack(fill="x")

        # 状态项布局
        status_items = [
            ("CPU温度：", self.current_cpu_temp),
            ("GPU温度：", self.current_gpu_temp),
            ("CPU风扇：", self.current_cpu_speed),
            ("GPU风扇：", self.current_gpu_speed),
            ("当前状态：", self.current_status)
        ]
        for i, (label_text, var) in enumerate(status_items):
            ttk.Label(status_grid, text=label_text, style="Header.TLabel").grid(
                row=0, column=i * 2, padx=(15, 5), pady=5, sticky="w")
            ttk.Label(status_grid, textvariable=var, style="Status.TLabel").grid(
                row=0, column=i * 2 + 1, padx=(0, 15), pady=5, sticky="w")

        # 中间模式选择区
        mode_frame = ttk.Frame(main_container)
        mode_frame.pack(fill="x", pady=(0, 10))

        # 系统性能模式卡片
        sys_mode_card = ttk.LabelFrame(mode_frame, text="系统性能模式", padding="10 10 10 10")
        sys_mode_card.pack(side="left", fill="x", expand=True, padx=(0, 5))

        sys_mode_grid = ttk.Frame(sys_mode_card)
        sys_mode_grid.pack(fill="x")

        ttk.Label(sys_mode_grid, text="选择性能模式：", style="Header.TLabel").pack(side="left", padx=(0, 15))
        self.sys_mode_buttons = {}
        for mode in ["狂暴模式", "静音游戏", "超长续航"]:
            btn = ttk.Button(
                sys_mode_grid,
                text=mode,
                command=lambda m=mode: self.set_system_perf_mode(m),
                width=10,
            )
            btn.pack(side="left", padx=5)
            self.sys_mode_buttons[mode] = btn

        # 风扇模式卡片（含强冷选项）
        fan_mode_card = ttk.LabelFrame(mode_frame, text="风扇控制模式", padding="10 10 10 10")
        fan_mode_card.pack(side="right", fill="x", expand=True, padx=(5, 0))

        fan_mode_grid = ttk.Frame(fan_mode_card)
        fan_mode_grid.pack(fill="x")

        # 基础风扇模式选择
        ttk.Label(fan_mode_grid, text="基础模式：", style="Header.TLabel").pack(side="left", padx=(0, 15))
        ttk.Radiobutton(
            fan_mode_grid,
            text="自动模式",
            variable=self.fan_mode_var,
            value="自动模式",
            command=self.switch_fan_mode,
            style="Custom.TRadiobutton"
        ).pack(side="left", padx=10)

        ttk.Radiobutton(
            fan_mode_grid,
            text="自定义模式",
            variable=self.fan_mode_var,
            value="自定义模式",
            command=self.switch_fan_mode,
            style="Custom.TRadiobutton"
        ).pack(side="left", padx=10)

        # 强冷模式开/关选项
        ttk.Label(fan_mode_grid, text="强冷模式：", style="Header.TLabel").pack(side="left", padx=(20, 15))
        ttk.Radiobutton(
            fan_mode_grid,
            text="开",
            variable=self.full_mode_choice,
            value="开",
            command=self._on_full_mode_change,
            style="Custom.TRadiobutton"
        ).pack(side="left", padx=5)

        ttk.Radiobutton(
            fan_mode_grid,
            text="关",
            variable=self.full_mode_choice,
            value="关",
            command=self._on_full_mode_change,
            style="Custom.TRadiobutton"
        ).pack(side="left", padx=5)

        # 底部内容区（曲线配置+预览）
        content_frame = ttk.Frame(main_container)
        content_frame.pack(fill="both", expand=True)

        # 左侧：曲线配置卡片
        config_card = ttk.LabelFrame(
            content_frame,
            text="风扇曲线配置（0-90度，每10度一个控制点）",
            padding="10 10 10 10"
        )
        config_card.pack(side="left", fill="both", expand=True, padx=(0, 10))

        # 配置说明
        ttk.Label(
            config_card,
            text="提示：修改数值后点击其他区域或按回车键自动生效（仅自定义模式可编辑）",
            foreground="#666",
            font=("微软雅黑", 10)
        ).pack(anchor="w", pady=(0, 10))

        # CPU曲线配置
        ttk.Label(config_card, text="CPU风扇曲线（温度℃: 转速%）", style="Header.TLabel").pack(anchor="w", pady=(10, 5))
        self.cpu_curve_entries = self._create_curve_entries(config_card, self.edit_cpu_curve, is_cpu=True)

        # GPU曲线配置
        ttk.Label(config_card, text="GPU风扇曲线（温度℃: 转速%）", style="Header.TLabel").pack(anchor="w", pady=(10, 5))
        self.gpu_curve_entries = self._create_curve_entries(config_card, self.edit_gpu_curve, is_cpu=False)

        # 低温阈值和配置管理
        ttk.Separator(config_card, orient="horizontal").pack(fill="x", pady=15)

        # 低温阈值设置
        threshold_frame = ttk.Frame(config_card)
        threshold_frame.pack(fill="x", pady=(0, 10))

        ttk.Label(threshold_frame, text="低温自动切换阈值：", style="Header.TLabel").pack(side="left", padx=(0, 10))
        self.threshold_entry = ttk.Entry(threshold_frame, width=5, font=("微软雅黑", 13))
        self.threshold_entry.insert(0, str(self.controller.low_temp_threshold))
        self.threshold_entry.pack(side="left", padx=(0, 5))
        ttk.Label(threshold_frame, text="℃（双温低于此值时自动切换为自动模式）").pack(side="left")
        self.threshold_entry.bind("<FocusOut>", self._on_threshold_change)
        self.threshold_entry.bind("<Return>", lambda e: self._handle_enter_key(e, is_threshold=True))

        # 配置文件管理按钮
        config_buttons_frame = ttk.Frame(config_card)
        config_buttons_frame.pack(fill="x", pady=(10, 0))

        ttk.Label(config_buttons_frame, text="配置管理：", style="Header.TLabel").pack(side="left", padx=(0, 10))
        # self.load_config_btn = ttk.Button(config_buttons_frame, text="加载配置", command=self.load_config,style="Custom.TButton")
        # self.load_config_btn.pack(side="left", padx=5)
        # self.save_as_config_btn = ttk.Button(config_buttons_frame, text="另存为...",
        #                                      command=lambda: self.save_config(as_new=True),style="Custom.TButton")
        # self.save_as_config_btn.pack(side="left", padx=5)
        self.restore_default_btn = ttk.Button(config_buttons_frame, text="恢复默认",
                                              command=self.restore_default_config,style="Custom.TButton")
        self.restore_default_btn.pack(side="left", padx=5)

        # 右侧：曲线预览卡片
        plot_card = ttk.LabelFrame(content_frame, text="曲线预览", padding="10 10 10 10")
        plot_card.pack(side="right", fill="both", expand=True, padx=(10, 0))

        self.plot_container = ttk.Frame(plot_card)
        self.plot_container.pack(fill="both", expand=True)

        # 底部操作区
        footer_frame = ttk.Frame(main_container)
        footer_frame.pack(fill="x", pady=10)

        ttk.Button(footer_frame, text="查看日志", command=self.view_current_log, style="Custom.TButton").pack(
            side="right", padx=5)
        # ttk.Button(footer_frame, text="保存日志副本", command=self.save_log, style="Custom.TButton").pack(side="right",
        #                                                                                                   padx=5)

        # 初始权限控制
        self._set_curve_editable(self.controller.is_custom_mode and not self.controller.is_full_mode)
        self._set_config_buttons_state(self.controller.is_custom_mode and not self.controller.is_full_mode)

        # 全局点击事件（处理输入框失焦）
        self.root.bind("<Button-1>", self._handle_global_click)

    def _create_curve_entries(self, parent, curve_data, is_cpu):
        """创建曲线配置输入框"""
        frame = ttk.Frame(parent)
        frame.pack(fill="x", pady=5)

        entries = {}
        max_per_row = 5  # 每行显示5个温度点
        sorted_items = sorted(curve_data.items())

        for i, (temp, speed) in enumerate(sorted_items):
            row = i // max_per_row
            col = i % max_per_row

            temp_frame = ttk.Frame(frame)
            temp_frame.grid(row=row, column=col, padx=10, pady=5, sticky="w")

            ttk.Label(temp_frame, text=f"{temp}℃:").pack(side="left", padx=(0, 5))
            entry = ttk.Entry(temp_frame, width=5, font=("微软雅黑", 13))
            entry.insert(0, str(speed))
            entry.pack(side="left")

            # 绑定事件
            entry.bind("<FocusOut>", lambda e, t=temp, cpu=is_cpu: self._on_curve_value_change(t, cpu))
            entry.bind("<Return>", lambda e, t=temp, cpu=is_cpu: self._handle_enter_key(e, t, cpu))
            entries[temp] = entry

        return entries

    def _handle_global_click(self, event):
        """全局点击事件：处理输入框失焦"""
        focused_widget = self.root.focus_get()
        if not focused_widget:
            return

        # 判断是否为曲线输入框或阈值输入框
        is_curve_entry = (focused_widget in self.cpu_curve_entries.values() or
                          focused_widget in self.gpu_curve_entries.values() or
                          focused_widget == self.threshold_entry)

        # 点击外部时失焦
        if is_curve_entry and event.widget != focused_widget:
            focused_widget.focus_set()
            self.root.focus()

    def _handle_enter_key(self, event, temp=None, is_cpu=None, is_threshold=False):
        """处理回车键：模拟失焦"""
        event.widget.update()
        if is_threshold:
            self._on_threshold_change(event)
        else:
            self._on_curve_value_change(temp, is_cpu)
        self.root.focus()

    def _on_curve_value_change(self, temp, is_cpu):
        """曲线值变化处理"""
        if not self.controller.is_custom_mode or self.controller.is_full_mode:
            return

        try:
            entries = self.cpu_curve_entries if is_cpu else self.gpu_curve_entries
            curve = self.edit_cpu_curve if is_cpu else self.edit_gpu_curve

            # 验证输入
            val = int(entries[temp].get())
            if not (0 <= val <= 100):
                raise ValueError("数值必须在0-100之间")

            # 更新曲线
            curve[temp] = val
            temp_index = temp // 10
            if is_cpu:
                self.controller.cpu_fans[temp_index] = val
                self.controller.applied_cpu_curve = self.edit_cpu_curve.copy()
            else:
                self.controller.gpu_fans[temp_index] = val
                self.controller.applied_gpu_curve = self.edit_gpu_curve.copy()

            # 刷新图表和保存配置
            self._update_plot()
            curve_type = "CPU" if is_cpu else "GPU"
            self.logger.info(f"{curve_type}风扇曲线更新：{temp}℃ → {val}%")
            success, msg = self.controller.save_config()
            if success:
                self.current_status.set(f"配置已更新 | {self.current_status.get().split(' | ')[-1]}")

        except ValueError as e:
            # 恢复原始值
            original_val = curve[temp]
            entries[temp].delete(0, tk.END)
            entries[temp].insert(0, str(original_val))
            error_msg = f"无效值：{str(e)}，已恢复原始值"
            self.logger.error(error_msg)
            messagebox.showerror("输入错误", error_msg)
        except Exception as e:
            error_msg = f"更新曲线失败：{str(e)}"
            self.logger.error(error_msg)
            messagebox.showerror("操作失败", error_msg)

    def save_config(self, as_new=False):
        """保存配置文件"""
        try:
            file_path = None
            if as_new:
                current_dir = os.path.dirname(os.path.abspath(__file__))
                file_path = filedialog.asksaveasfilename(
                    defaultextension=".json",
                    filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")],
                    initialdir=current_dir,
                    title="保存风扇配置"
                )
                if not file_path:
                    return

            success, msg = self.controller.save_config(file_path)
            if success:
                self.logger.info(f"配置已保存至：{msg}")
                messagebox.showinfo("成功", f"配置已保存至：\n{msg}")
            else:
                self.logger.error(f"保存配置失败：{msg}")
                messagebox.showerror("失败", f"保存配置失败：{msg}")
        except Exception as e:
            error_msg = f"保存配置时出错：{str(e)}"
            self.logger.error(error_msg)
            messagebox.showerror("错误", error_msg)

    def load_config(self):
        """加载配置文件"""
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            file_path = filedialog.askopenfilename(
                defaultextension=".json",
                filetypes=[("JSON文件", "*.json")],
                initialdir=current_dir,
                title="加载风扇配置"
            )
            if not file_path:
                return

            success, msg = self.controller.load_config(file_path)
            if success:
                # 更新编辑缓存和输入框
                self.edit_cpu_curve = self.controller.applied_cpu_curve.copy()
                self.edit_gpu_curve = self.controller.applied_gpu_curve.copy()
                for temp, entry in self.cpu_curve_entries.items():
                    entry.delete(0, tk.END)
                    entry.insert(0, str(self.edit_cpu_curve[temp]))
                for temp, entry in self.gpu_curve_entries.items():
                    entry.delete(0, tk.END)
                    entry.insert(0, str(self.edit_gpu_curve[temp]))

                # 更新阈值和模式选择
                self.threshold_entry.delete(0, tk.END)
                self.threshold_entry.insert(0, str(self.controller.low_temp_threshold))
                self.fan_mode_var.set("自定义模式" if self.controller.current_fan_mode == "manual" else "自动模式")
                self.full_mode_choice.set("开" if self.controller.is_full_mode else "关")

                # 刷新图表和权限
                self._update_plot()
                self._set_curve_editable(self.controller.is_custom_mode and not self.controller.is_full_mode)
                self._set_config_buttons_state(self.controller.is_custom_mode and not self.controller.is_full_mode)

                self.logger.info(f"已加载配置：{msg}")
                messagebox.showinfo("成功", f"已加载配置：\n{msg}")
            else:
                self.logger.error(f"加载配置失败：{msg}")
                messagebox.showerror("失败", f"加载配置失败：{msg}")
        except Exception as e:
            error_msg = f"加载配置时出错：{str(e)}"
            self.logger.error(error_msg)
            messagebox.showerror("错误", error_msg)

    def restore_default_config(self):
        """恢复默认配置"""
        if messagebox.askyesno("确认恢复默认", "确定要恢复默认风扇曲线和设置吗？"):
            try:
                self.controller._load_default_config()
                self.controller.low_temp_threshold = 20
                self.controller.current_fan_mode = "manual"
                self.controller.is_custom_mode = True
                self.controller.is_full_mode = False

                # 更新编辑缓存和输入框
                self.edit_cpu_curve = self.controller.applied_cpu_curve.copy()
                self.edit_gpu_curve = self.controller.applied_gpu_curve.copy()
                for temp, entry in self.cpu_curve_entries.items():
                    entry.delete(0, tk.END)
                    entry.insert(0, str(self.edit_cpu_curve[temp]))
                for temp, entry in self.gpu_curve_entries.items():
                    entry.delete(0, tk.END)
                    entry.insert(0, str(self.edit_gpu_curve[temp]))

                # 更新阈值和模式选择
                self.threshold_entry.delete(0, tk.END)
                self.threshold_entry.insert(0, str(self.controller.low_temp_threshold))
                self.fan_mode_var.set("自定义模式")
                self.full_mode_choice.set("关")

                # 刷新图表和权限
                self._update_plot()
                self._set_curve_editable(True)
                self._set_config_buttons_state(True)

                # 保存配置
                self.controller.save_config()
                self.logger.info("已恢复默认配置")
                messagebox.showinfo("成功", "已恢复默认风扇曲线和设置")
            except Exception as e:
                error_msg = f"恢复默认配置失败：{str(e)}"
                self.logger.error(error_msg)
                messagebox.showerror("失败", error_msg)

    def _on_threshold_change(self, event):
        """低温阈值变化处理"""
        if not self.controller.is_custom_mode or self.controller.is_full_mode:
            return

        try:
            new_threshold = int(self.threshold_entry.get())
            if not (0 <= new_threshold <= 100):
                raise ValueError("阈值必须在0-100℃之间")

            self.controller.low_temp_threshold = new_threshold
            self.logger.info(f"低温阈值更新：{new_threshold}℃")
            self.controller.save_config()
        except ValueError as e:
            # 恢复原始值
            self.threshold_entry.delete(0, tk.END)
            self.threshold_entry.insert(0, str(self.controller.low_temp_threshold))
            error_msg = f"无效阈值：{str(e)}，已恢复原始值"
            self.logger.error(error_msg)
            messagebox.showerror("输入错误", error_msg)
        except Exception as e:
            error_msg = f"更新阈值失败：{str(e)}"
            self.logger.error(error_msg)
            messagebox.showerror("操作失败", error_msg)

    def _set_curve_editable(self, editable):
        """设置曲线编辑区域是否可编辑"""
        state = "normal" if editable else "disabled"
        for entry in self.cpu_curve_entries.values():
            entry.config(state=state)
        for entry in self.gpu_curve_entries.values():
            entry.config(state=state)
        self.threshold_entry.config(state=state)

    def _set_config_buttons_state(self, enabled):
        """设置配置按钮状态"""
        state = "normal" if enabled else "disabled"
        # self.load_config_btn.config(state=state)
        # self.save_as_config_btn.config(state=state)
        self.restore_default_btn.config(state=state)

    def _init_plot(self):
        """初始化曲线预览图"""
        self.fig, self.ax = plt.subplots(figsize=(5, 4), facecolor='none')
        self.ax.set_facecolor('#f8f9fa')
        self.ax.set_xlabel('温度（℃）', fontsize=10)
        self.ax.set_ylabel('风扇转速（%）', fontsize=10)
        self.ax.set_title('风扇曲线预览', fontsize=12, fontweight='bold')

        # 坐标轴设置
        self.ax.set_xticks(range(0, 105, 10))
        self.ax.set_yticks(range(0, 105, 10))
        self.ax.set_xlim(0, 100)
        self.ax.set_ylim(0, 100)
        self.ax.grid(True, alpha=0.3)

        # 画布初始化
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.plot_container)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

        # 曲线和点标记
        self.cpu_line, = self.ax.plot([], [], 'r-', linewidth=2.5, label='CPU风扇', alpha=0.85)
        self.cpu_points, = self.ax.plot([], [], 'ro', markersize=7, alpha=0.85, markeredgecolor='darkred')
        self.gpu_line, = self.ax.plot([], [], 'b-', linewidth=2.5, label='GPU风扇', alpha=0.85)
        self.gpu_points, = self.ax.plot([], [], 'bs', markersize=7, alpha=0.85, markeredgecolor='darkblue')
        self.ax.legend(loc='lower right', fontsize=9)

    def _update_plot(self):
        """更新曲线预览图"""
        try:
            # 更新CPU曲线
            cpu_temps = sorted(self.edit_cpu_curve.keys())
            cpu_speeds = [self.edit_cpu_curve[t] for t in cpu_temps]
            self.cpu_line.set_data(cpu_temps, cpu_speeds)
            self.cpu_points.set_data(cpu_temps, cpu_speeds)

            # 更新GPU曲线
            gpu_temps = sorted(self.edit_gpu_curve.keys())
            gpu_speeds = [self.edit_gpu_curve[t] for t in gpu_temps]
            self.gpu_line.set_data(gpu_temps, gpu_speeds)
            self.gpu_points.set_data(gpu_temps, gpu_speeds)

            self.canvas.draw()
        except Exception as e:
            error_msg = f"更新图表失败：{str(e)}"
            self.logger.error(error_msg)
            messagebox.showerror("图表错误", error_msg)

    def _query_current_mode(self):
        """查询并更新系统性能模式"""
        try:
            mode_name, _ = self.controller.query_current_mode()
            # 更新按钮样式
            for btn_name, btn in self.sys_mode_buttons.items():
                btn.config(style="Accent.TButton" if btn_name == mode_name else "TButton")
            self.update_status_text()
            self.logger.info(f"当前系统模式：{mode_name}")
            return True
        except Exception as e:
            error_msg = f"查询模式失败：{str(e)}"
            self.logger.error(error_msg)
            self.current_status.set(f"模式查询失败：{str(e)}")
            return False

    def _get_current_fan_mode_text(self):
        """获取当前风扇模式的显示文本"""
        if self.controller.is_full_mode:
            return "强冷模式（全速）"
        elif self.controller.is_custom_mode:
            return "自定义风扇"
        else:
            return "自动风扇"

    def update_status_text(self):
        """更新状态文本"""

        def update():
            current_perf = self.controller.current_perf_mode
            current_fan = self._get_current_fan_mode_text()

            # 检测状态变化并记录日志
            if current_perf != self.last_perf_mode or current_fan != self.last_fan_mode:
                self.logger.info(f"状态更新：{current_perf} | {current_fan}")
                self.last_perf_mode = current_perf
                self.last_fan_mode = current_fan

            self.current_status.set(f"就绪（{current_perf} | {current_fan}）")

        self.root.after(0, update)

    def set_system_perf_mode(self, mode_name):
        """切换系统性能模式"""
        try:
            result = self.controller.set_system_perf_mode(mode_name)
            if self._query_current_mode():
                self.logger.info(f"切换至{mode_name}成功（返回值：{result}）")
        except Exception as e:
            error_msg = f"切换{mode_name}失败：{str(e)}"
            self.logger.error(error_msg)
            messagebox.showerror("切换失败", error_msg)

    def switch_fan_mode(self):
        """切换基础风扇模式（自动/自定义）"""
        selected_mode = self.fan_mode_var.get()
        mode_code = self.fan_mode_mapping.get(selected_mode)

        if not mode_code:
            logging.error(f"无效模式：{selected_mode}")
            return

        try:
            self.controller.switch_fan_mode(mode_code)
            # 更新权限
            is_editable = mode_code == "manual" and not self.controller.is_full_mode
            self._set_curve_editable(is_editable)
            self._set_config_buttons_state(is_editable)
            self.update_status_text()
        except Exception as e:
            error_msg = f"切换风扇模式失败：{str(e)}"
            self.logger.error(error_msg)
            messagebox.showerror("切换失败", error_msg)
            # 恢复选择
            current_mode = self.controller.current_fan_mode
            self.fan_mode_var.set(self.reverse_fan_mapping.get(current_mode, "自动模式"))

    def _on_full_mode_change(self):
        """处理强冷模式开/关切换"""
        choice = self.full_mode_choice.get()
        target_enable = (choice == "开")

        # 状态未变化则不处理
        if target_enable == self.controller.is_full_mode:
            return

        # 备份当前状态用于回滚
        old_full = self.controller.is_full_mode
        old_fan_mode = self.controller.current_fan_mode
        old_custom = self.controller.is_custom_mode

        try:
            # 切换强冷模式
            self.controller.toggle_full_mode(target_enable)

            # 更新权限
            is_editable = self.controller.is_custom_mode and not target_enable
            self._set_curve_editable(is_editable)
            self._set_config_buttons_state(is_editable)

            # 强冷关闭时恢复基础模式显示
            if not target_enable:
                self.fan_mode_var.set(
                    "自定义模式" if self.controller.current_fan_mode == "manual" else "自动模式"
                )

            self.update_status_text()
        except Exception as e:
            # 回滚状态
            error_msg = f"强冷模式切换失败：{str(e)}"
            self.logger.error(error_msg)
            self.controller.is_full_mode = old_full
            self.controller.current_fan_mode = old_fan_mode
            self.controller.is_custom_mode = old_custom
            self.full_mode_choice.set("开" if old_full else "关")
            self.fan_mode_var.set("自定义模式" if old_custom else "自动模式")
            self._set_curve_editable(old_custom and not old_full)
            messagebox.showerror("操作失败", error_msg)

    def start_monitoring(self):
        """启动温度和转速监控"""
        if not self.is_monitoring:
            self.is_monitoring = True
            self.monitor_thread = threading.Thread(target=self.monitor_loop, daemon=True)
            self.monitor_thread.start()
            self.logger.info("监控线程已启动")

    def monitor_loop(self):
        """监控主循环"""
        while self.is_monitoring:
            try:
                # 查询性能模式
                self.controller.query_current_mode()

                # 同步强冷模式状态
                self._sync_full_mode_status()

                # 获取温度和转速
                temps = self.controller.get_temperatures()
                speeds = self.controller.get_fan_speeds()

                # 更新UI显示
                self.root.after(0, lambda t=temps: self.current_cpu_temp.set(f"{t['cpu']}℃"))
                self.root.after(0, lambda t=temps: self.current_gpu_temp.set(f"{t['gpu']}℃"))
                self.root.after(0, lambda s=speeds: self.current_cpu_speed.set(f"{s['cpu']}转"))
                self.root.after(0, lambda s=speeds: self.current_gpu_speed.set(f"{s['gpu']}转"))
                self.root.after(0, self.update_status_text)
                self.root.after(0, self._update_perf_mode_buttons)

                # 生成日志
                if self.controller.is_full_mode:
                    log_msg = f"CPU: {temps['cpu']}℃ | GPU: {temps['gpu']}℃ | 强冷模式 | 系统模式：{self.controller.current_perf_mode}"
                elif self.controller.is_custom_mode:
                    control_log, _ = self.controller.custom_fan_control(temps)
                    log_msg = f"CPU: {temps['cpu']}℃ [{speeds['cpu']}转] | GPU: {temps['gpu']}℃ [{speeds['gpu']}转] | {control_log} | 系统模式：{self.controller.current_perf_mode}"
                else:
                    log_msg = f"CPU: {temps['cpu']}℃ 自动 [{speeds['cpu']}转] | GPU: {temps['gpu']}℃ 自动 [{speeds['gpu']}转] | 系统模式：{self.controller.current_perf_mode}"

                self.logger.info(log_msg)

            except Exception as e:
                error_msg = f"监控错误：{str(e)}"
                self.logger.error(error_msg)
                self.root.after(0, lambda msg=error_msg: self.current_status.set(f"错误：{msg}"))

            # 等待下一次监控
            time.sleep(self.controller.monitor_interval)

    def _sync_full_mode_status(self):
        """同步强冷模式状态（处理外部修改）"""
        try:
            current_status = self.controller.wmi.GetFanFullMode()
            new_full_mode = current_status != 0

            if new_full_mode != self.controller.is_full_mode:
                self.controller.is_full_mode = new_full_mode
                self.full_mode_choice.set("开" if new_full_mode else "关")

                # 强冷关闭时恢复基础模式显示
                if not new_full_mode:
                    self.fan_mode_var.set(
                        "自定义模式" if self.controller.current_fan_mode == "manual" else "自动模式"
                    )

                # 更新权限
                is_editable = self.controller.is_custom_mode and not new_full_mode
                self.root.after(0, lambda: self._set_curve_editable(is_editable))
                self.root.after(0, lambda: self._set_config_buttons_state(is_editable))

                logging.info(f"强冷模式同步：{'开' if new_full_mode else '关'}")
        except Exception as e:
            logging.warning(f"同步强冷模式失败: {str(e)}")

    def _update_perf_mode_buttons(self):
        """更新性能模式按钮样式"""
        for btn_name, btn in self.sys_mode_buttons.items():
            btn.config(style="Accent.TButton" if btn_name == self.controller.current_perf_mode else "TButton")

    def view_current_log(self):
        """查看当前日志"""
        try:
            if self.log_window and self.log_window.winfo_exists():
                self.log_window.lift()
                return

            # 获取日志文件路径
            log_file = None
            for handler in self.logger.handlers:
                if isinstance(handler, RotatingFileHandler):
                    log_file = handler.baseFilename
                    break

            if not log_file or not os.path.exists(log_file):
                raise Exception("日志文件不存在")

            # 创建日志窗口
            self.log_window = tk.Toplevel(self.root)
            self.log_window.title(f"日志查看 - {os.path.basename(log_file)}")
            self.log_window.geometry("1200x600")
            self.log_window.minsize(1080, 400)

            # 窗口关闭处理
            def on_close():
                self.stop_log_refresh()
                self.log_window.destroy()
                self.log_window = None

            self.log_window.protocol("WM_DELETE_WINDOW", on_close)

            # 日志显示区域
            log_frame = ttk.LabelFrame(self.log_window, text="日志内容（实时更新）", padding=10)
            log_frame.pack(fill="both", expand=True, padx=10, pady=10)

            self.log_text = tk.Text(log_frame, wrap=tk.WORD, font=("Consolas", 13))
            self.log_text.pack(side="left", fill="both", expand=True)

            scroll = ttk.Scrollbar(log_frame, command=self.log_text.yview)
            scroll.pack(side="right", fill="y")
            self.log_text.config(yscrollcommand=scroll.set)

            # 加载日志并启动刷新
            self.refresh_log_content()
            self.start_log_refresh()

        except Exception as e:
            error_msg = f"查看日志失败：{str(e)}"
            self.logger.error(error_msg)
            messagebox.showerror("失败", error_msg)

    def start_log_refresh(self):
        """启动日志刷新"""
        if not self.log_refresh_active:
            self.log_refresh_active = True
            self.log_refresh_loop()

    def stop_log_refresh(self):
        """停止日志刷新"""
        self.log_refresh_active = False

    def log_refresh_loop(self):
        """日志刷新循环"""
        if self.log_refresh_active and self.log_window and self.log_window.winfo_exists():
            self.refresh_log_content()
            self.root.after(500, self.log_refresh_loop)  # 500ms刷新一次

    def refresh_log_content(self):
        """刷新日志内容"""
        try:
            if not hasattr(self, 'log_text') or not self.log_window:
                return

            # 获取日志文件
            log_file = None
            for handler in self.logger.handlers:
                if isinstance(handler, RotatingFileHandler):
                    log_file = handler.baseFilename
                    break

            if not log_file or not os.path.exists(log_file):
                return

            # 保存滚动位置
            current_pos = self.log_text.yview()[1]
            is_at_end = current_pos > 0.95

            # 读取并显示日志
            with open(log_file, "r", encoding="utf-8") as f:
                content = f.read()

            self.log_text.config(state="normal")
            self.log_text.delete(1.0, tk.END)
            self.log_text.insert(tk.END, content)
            if is_at_end:
                self.log_text.see(tk.END)
            self.log_text.config(state="disabled")

        except Exception as e:
            print(f"刷新日志失败：{str(e)}")

    def save_log(self):
        """保存日志副本"""
        try:
            log_file = None
            for handler in self.logger.handlers:
                if isinstance(handler, RotatingFileHandler):
                    log_file = handler.baseFilename
                    break

            if not log_file or not os.path.exists(log_file):
                raise Exception("日志文件不存在")

            # 读取日志内容
            with open(log_file, "r", encoding="utf-8") as f:
                content = f.read()

            # 保存为新文件
            new_file = f"fan_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            new_path = get_file_path("new_file")
            with open(new_path, "w", encoding="utf-8") as f:
                f.write(content)

            self.logger.info(f"日志已保存至：{new_file}")
            messagebox.showinfo("成功", f"日志副本已保存至：\n{new_path}")
        except Exception as e:
            error_msg = f"保存日志失败：{str(e)}"
            self.logger.error(error_msg)
            messagebox.showerror("失败", error_msg)

    def on_close(self):
        """程序关闭处理"""
        self.is_monitoring = False
        self.stop_log_refresh()
        if hasattr(self, 'monitor_thread') and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=1.0)
        self.controller.restore_default_mode()  # 恢复默认风扇模式
        self.controller.save_config()  # 保存最终配置
        self.logger.info("程序已关闭")
        plt.close(self.fig)  # 关闭图表
        self.root.destroy()


def init_logging():
    """初始化日志系统"""
    log_filename = f"fan_control_log_{datetime.now().strftime('%Y%m%d')}.txt"
    log_path = get_file_path(log_filename)

    log_format = logging.Formatter('%(asctime)s - %(message)s', datefmt='%H:%M:%S')
    log_handler = RotatingFileHandler(
        log_path,
        maxBytes=1024 * 1024,  # 1MB
        backupCount=5,
        encoding='utf-8'
    )
    log_handler.setFormatter(log_format)

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.addHandler(log_handler)

    return logger


if __name__ == "__main__":
    # 初始化日志# 调整tk控件字体大小

    logger = init_logging()

    try:
        # 初始化风扇控制器（加载DLL和硬件交互）
        controller = FanController()

        # 创建主窗口并启动GUI
        root = tk.Tk()

        logo_img = PhotoImage(file=get_file_path("iGame.png"))  # 加载图片
        root.iconphoto(True, logo_img)
        # 用 Label 显示图片
        # logo_label = tk.Label(root, image=logo_img)
        # logo_label.pack(padx=1, pady=1)

        default_font = ('SimHei', 13)  # 主字体大小
        root.option_add('*Font', default_font)

        app = FanCurveGUI(root, controller, logger)

        # 绑定窗口关闭事件（确保资源正确释放）
        root.protocol("WM_DELETE_WINDOW", app.on_close)

        # 启动主事件循环
        root.mainloop()

    except Exception as e:
        # 捕获启动阶段的致命错误
        error_msg = f"程序启动失败：{str(e)}"
        logger.error(error_msg)
        messagebox.showerror("启动失败", error_msg)
        # 确保程序退出
        import sys

        sys.exit(1)
