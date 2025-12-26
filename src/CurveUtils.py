import tkinter as tk
from tkinter import ttk, messagebox
import matplotlib

matplotlib.use('TkAgg')  # 强制指定Tk后端，避免渲染冲突
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import numpy as np

# 设置中文字体和matplotlib样式
plt.rcParams["font.family"] = ["SimHei"]
plt.rcParams["axes.unicode_minus"] = False
# 紧凑布局参数
plt.rcParams['figure.subplot.bottom'] = 0.15
plt.rcParams['figure.subplot.left'] = 0.1
plt.rcParams['figure.subplot.right'] = 0.9
plt.rcParams['figure.subplot.top'] = 0.85
plt.rcParams['figure.subplot.wspace'] = 0.1  # 子图紧凑间距


class FanCurveWidget(tk.Frame):
    """
    风扇曲线编辑组件（修复维度错误+100℃刻度+置灰功能）
    特性：100℃刻度、子图紧凑、90℃易操作、数据维度安全校验、不可编辑时图表置灰
    """

    def __init__(self, master=None, cpu_data=None, gpu_data=None, **kwargs):
        super().__init__(master, **kwargs)

        # 固定温度点（0-90℃，步长10）- 核心：保持10个点的基础数据
        self.fixed_temps = list(range(0, 91, 10))
        # 显示刻度（包含100℃）
        self.display_ticks = list(range(0, 101, 10))  # 0,10,...,90,100

        # ========== 核心修复：强制数据维度校验和初始化 ==========
        # 初始化数据（确保是10个点的列表）
        default_cpu = [0, 38, 38, 38, 38, 47, 55, 64, 74, 83]
        default_gpu = [0, 38, 38, 38, 38, 47, 55, 64, 74, 83]

        # 严格校验输入数据维度
        if isinstance(cpu_data, list) and len(cpu_data) == 10:
            self._cpu_speed = cpu_data.copy()
        elif isinstance(cpu_data, dict) and len(cpu_data) == 10:
            self._cpu_speed = list(cpu_data.values()).copy()
        else:
            self._cpu_speed = default_cpu.copy()

        if isinstance(gpu_data, list) and len(gpu_data) == 10:
            self._gpu_speed = gpu_data.copy()
        elif isinstance(gpu_data, dict) and len(gpu_data) == 10:
            self._gpu_speed = list(gpu_data.values()).copy()
        else:
            self._gpu_speed = default_gpu.copy()

        # 拖拽状态
        self.dragging_curve = None
        self.dragging_idx = None
        self.has_dragging_change = False

        # 可编辑状态
        self.editable = True  # 是否可编辑

        # 颜色配置
        self.normal_colors = {
            'cpu': '#E74C3C',
            'gpu': '#27AE60',
            'grid': '#EEEEEE',
            'spine': '#CCCCCC',
            'text': '#333333'
        }
        self.gray_colors = {
            'cpu': '#A0A0A0',
            'gpu': '#888888',
            'grid': '#F0F0F0',
            'spine': '#DDDDDD',
            'text': '#999999'
        }

        # 控制点配置
        self.point_size = 6
        self.detect_radius = 14
        self.picker_tolerance = 18

        # 画布尺寸
        self.fig = plt.Figure(figsize=(7, 4), dpi=100)
        self.ax_cpu = self.fig.add_subplot(121)
        self.ax_gpu = self.fig.add_subplot(122)

        # 绘图对象初始化（避免空引用）
        self.cpu_line = None
        self.cpu_points = None
        self.gpu_line = None
        self.gpu_points = None

        # 创建画布
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)

        # 绑定事件
        self._bind_events()

        # 初始化绘图
        self._init_plot_elements()
        self.update_plot_data()
        self.canvas.draw()

        # 数据回调
        self.on_data_change = None

    @property
    def cpu_data(self):
        return self._cpu_speed.copy()

    @property
    def gpu_data(self):
        return self._gpu_speed.copy()

    def set_editable(self, editable):
        """
        设置是否可编辑
        :param editable: True-可编辑，False-不可编辑（置灰）
        """
        self.editable = editable

        # 更新鼠标样式
        if editable:
            self.canvas_widget.config(cursor="hand2")
            self.canvas_widget.bind('<Enter>', lambda e: self.canvas_widget.config(cursor="hand2"))
        else:
            self.canvas_widget.config(cursor="arrow")
            self.canvas_widget.bind('<Enter>', lambda e: self.canvas_widget.config(cursor="arrow"))

        # 重新绘制图表（应用置灰/恢复颜色）
        self._init_plot_elements()
        self.update_plot_data()
        self.canvas.draw()

    def set_data(self, cpu_data=None, gpu_data=None):
        """核心修复：设置数据时强制维度校验"""
        # 如果不可编辑，不允许修改数据
        if not self.editable:
            return

        # CPU数据校验（必须是10个点）
        if isinstance(cpu_data, list) and len(cpu_data) == 10:
            self._cpu_speed = [0 if i == 0 else max(0, min(int(round(val)), 100))
                               for i, val in enumerate(cpu_data)]
        # GPU数据校验（必须是10个点）
        if isinstance(gpu_data, list) and len(gpu_data) == 10:
            self._gpu_speed = [0 if i == 0 else max(0, min(int(round(val)), 100))
                               for i, val in enumerate(gpu_data)]

        self.update_plot_data()
        self._trigger_data_change()

    def _trigger_data_change(self):
        if self.on_data_change:
            applied_cpu_curve = {i * 10: self.cpu_data[i] for i in range(10)}
            applied_gpu_curve = {i * 10: self.gpu_data[i] for i in range(10)}
            self.after_idle(lambda: self.on_data_change(applied_cpu_curve, applied_gpu_curve))

    def _init_plot_elements(self):
        """初始化绘图元素（确保x/y维度匹配）"""
        # 获取当前颜色配置
        colors = self.normal_colors if self.editable else self.gray_colors

        # CPU子图（左）
        self.ax_cpu.clear()
        self._init_subplot_style(self.ax_cpu, "CPU 风扇曲线", colors)

        # ========== 关键：x是fixed_temps(10个点)，y是_cpu_speed(10个点) ==========
        self.cpu_line, = self.ax_cpu.plot(self.fixed_temps, self._cpu_speed,
                                          color=colors['cpu'], linewidth=2, alpha=0.9 if self.editable else 0.7)
        self.cpu_points, = self.ax_cpu.plot(self.fixed_temps, self._cpu_speed,
                                            color=colors['cpu'], marker='o', markersize=self.point_size,
                                            markerfacecolor=colors['cpu'], markeredgecolor='white',
                                            markeredgewidth=1.2,
                                            linestyle='None',
                                            picker=self.picker_tolerance if self.editable else 0)

        # GPU子图（右）
        self.ax_gpu.clear()
        self._init_subplot_style(self.ax_gpu, "GPU 风扇曲线", colors)
        self.gpu_line, = self.ax_gpu.plot(self.fixed_temps, self._gpu_speed,
                                          color=colors['gpu'], linewidth=2, alpha=0.9 if self.editable else 0.7)
        self.gpu_points, = self.ax_gpu.plot(self.fixed_temps, self._gpu_speed,
                                            color=colors['gpu'], marker='o', markersize=self.point_size,
                                            markerfacecolor=colors['gpu'], markeredgecolor='white',
                                            markeredgewidth=1.2,
                                            linestyle='None',
                                            picker=self.picker_tolerance if self.editable else 0)

    def _init_subplot_style(self, ax, title, colors):
        """添加100℃刻度的子图样式（支持置灰）"""
        # 90℃右侧空白保留（X轴到100）
        ax.set_xlim(-5, 105)  # 轻微扩展，避免100℃刻度贴边
        ax.set_ylim(-5, 105)
        ax.set_aspect('equal', adjustable='box')

        # ========== 添加100℃刻度 ==========
        ax.set_xticks(self.display_ticks)  # 0-100℃，步长10
        ax.set_yticks(range(0, 101, 10))
        ax.minorticks_off()
        ax.tick_params(labelsize=9, colors=colors['text'])

        # 坐标轴样式
        ax.spines['left'].set_position(('data', 0))
        ax.spines['bottom'].set_position(('data', 0))
        ax.spines['left'].set_color(colors['spine'])
        ax.spines['bottom'].set_color(colors['spine'])
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)

        # 网格设置（包含100℃刻度的网格）
        ax.grid(True, which='major', axis='both',
                color=colors['grid'], alpha=0.8 if self.editable else 0.5,
                linewidth=1, linestyle='--')

        # 紧凑标签
        ax.set_xlabel("温度 (℃)", fontsize=9, color=colors['text'], labelpad=3)
        ax.set_ylabel("转速 (%)", fontsize=9, color=colors['text'], labelpad=3)
        ax.set_title(title, fontsize=10, color=colors['text'], pad=3, fontweight='bold')

    def update_plot_data(self):
        """更新数据：强制校验维度"""
        # 安全校验：确保数据是10个点
        if len(self._cpu_speed) != 10:
            self._cpu_speed = [0, 20, 25, 30, 40, 50, 60, 70, 80, 90]
        if len(self._gpu_speed) != 10:
            self._gpu_speed = [0, 25, 30, 40, 50, 60, 70, 80, 90, 95]

        # 数据范围校验
        self._cpu_speed[0] = 0
        self._gpu_speed[0] = 0
        self._cpu_speed = [max(0, min(int(round(val)), 100)) for val in self._cpu_speed]
        self._gpu_speed = [max(0, min(int(round(val)), 100)) for val in self._gpu_speed]

        # 获取当前颜色配置
        colors = self.normal_colors if self.editable else self.gray_colors

        # 更新绘图数据（确保x/y维度匹配）
        if self.cpu_line:
            self.cpu_line.set_ydata(self._cpu_speed)
            self.cpu_line.set_color(colors['cpu'])
            self.cpu_line.set_alpha(0.9 if self.editable else 0.7)
        if self.cpu_points:
            self.cpu_points.set_ydata(self._cpu_speed)
            self.cpu_points.set_color(colors['cpu'])
            self.cpu_points.set_markerfacecolor(colors['cpu'])
            self.cpu_points.set_picker(self.picker_tolerance if self.editable else 0)
        if self.gpu_line:
            self.gpu_line.set_ydata(self._gpu_speed)
            self.gpu_line.set_color(colors['gpu'])
            self.gpu_line.set_alpha(0.9 if self.editable else 0.7)
        if self.gpu_points:
            self.gpu_points.set_ydata(self._gpu_speed)
            self.gpu_points.set_color(colors['gpu'])
            self.gpu_points.set_markerfacecolor(colors['gpu'])
            self.gpu_points.set_picker(self.picker_tolerance if self.editable else 0)

        # 刷新画布
        self.canvas.draw_idle()

    def _bind_events(self):
        """绑定拖拽事件"""
        self.canvas.mpl_connect('button_press_event', self._on_mouse_press)
        self.canvas.mpl_connect('motion_notify_event', self._on_mouse_move)
        self.canvas.mpl_connect('button_release_event', self._on_mouse_release)

        self.canvas_widget.bind('<Enter>', lambda e: self.canvas_widget.config(
            cursor="hand2" if self.editable else "arrow"
        ))
        self.canvas_widget.bind('<Leave>', lambda e: self.canvas_widget.config(cursor="arrow"))

    def _on_mouse_press(self, event):
        """选中控制点（不可编辑时不响应）"""
        if not self.editable:
            return

        self.dragging_curve = None
        self.dragging_idx = None
        self.has_dragging_change = False

        if not event.inaxes or event.xdata is None or event.ydata is None:
            return

        # 温度点匹配（支持100℃区域点击90℃点）
        temp = round(event.xdata)
        temp = np.clip(temp, 0, 90)  # 限制在0-90（有效数据点范围）
        closest_idx = min(range(len(self.fixed_temps)),
                          key=lambda i: abs(self.fixed_temps[i] - temp))
        closest_temp = self.fixed_temps[closest_idx]

        if closest_temp < 0 or closest_temp > 90 or closest_idx == 0:
            return

        # 判断子图
        if event.inaxes == self.ax_cpu:
            cpu_x, cpu_y = self.fixed_temps[closest_idx], self._cpu_speed[closest_idx]
            cpu_dist = np.hypot(event.xdata - cpu_x, event.ydata - cpu_y)
            if cpu_dist < self.detect_radius:
                self.dragging_curve = 'cpu'
                self.dragging_idx = closest_idx
        elif event.inaxes == self.ax_gpu:
            gpu_x, gpu_y = self.fixed_temps[closest_idx], self._gpu_speed[closest_idx]
            gpu_dist = np.hypot(event.xdata - gpu_x, event.ydata - gpu_y)
            if gpu_dist < self.detect_radius:
                self.dragging_curve = 'gpu'
                self.dragging_idx = closest_idx

    def _on_mouse_move(self, event):
        """拖拽控制点（不可编辑时不响应）"""
        if not self.editable:
            return

        if self.dragging_curve and self.dragging_idx is not None:
            if not event.inaxes or event.ydata is None:
                return

            new_y = int(round(event.ydata))
            new_y = max(0, min(new_y, 100))

            # 确保索引有效
            if 0 <= self.dragging_idx < len(self._cpu_speed):
                if self.dragging_curve == 'cpu' and self._cpu_speed[self.dragging_idx] != new_y:
                    self._cpu_speed[self.dragging_idx] = new_y
                    self.has_dragging_change = True
                    self.update_plot_data()
            if 0 <= self.dragging_idx < len(self._gpu_speed):
                if self.dragging_curve == 'gpu' and self._gpu_speed[self.dragging_idx] != new_y:
                    self._gpu_speed[self.dragging_idx] = new_y
                    self.has_dragging_change = True
                    self.update_plot_data()

    def _on_mouse_release(self, event):
        """释放鼠标（不可编辑时不响应）"""
        if not self.editable:
            return

        if self.has_dragging_change:
            self._trigger_data_change()

        self.dragging_curve = None
        self.dragging_idx = None
        self.has_dragging_change = False


# ------------------- 测试代码 -------------------
if __name__ == "__main__":
    root = tk.Tk()
    root.title("风扇曲线编辑器 - 修复维度错误+100℃刻度+置灰功能")
    root.geometry("800x550")

    # 数据显示区域
    data_frame = ttk.LabelFrame(root, text="实时数据监控（0-90℃）", padding=8)
    data_frame.pack(fill=tk.X, padx=8, pady=5)

    cpu_label = ttk.Label(data_frame, text="CPU曲线数据：")
    cpu_label.grid(row=0, column=0, sticky=tk.W, padx=4)
    cpu_data_var = tk.StringVar()
    cpu_data_label = ttk.Label(data_frame, textvariable=cpu_data_var, font=("Consolas", 8))
    cpu_data_label.grid(row=0, column=1, sticky=tk.W, padx=4)

    gpu_label = ttk.Label(data_frame, text="GPU曲线数据：")
    gpu_label.grid(row=1, column=0, sticky=tk.W, padx=4)
    gpu_data_var = tk.StringVar()
    gpu_data_label = ttk.Label(data_frame, textvariable=gpu_data_var, font=("Consolas", 8))
    gpu_data_label.grid(row=1, column=1, sticky=tk.W, padx=4)

    # 编辑状态显示
    edit_status_var = tk.StringVar(value="当前状态：曲线可编辑（彩色显示）")
    edit_status_label = ttk.Label(
        data_frame,
        textvariable=edit_status_var,
        font=("SimHei", 9),
        foreground="green"
    )
    edit_status_label.grid(row=2, column=0, columnspan=2, pady=4)


    # 数据回调
    def on_data_change(cpu, gpu):
        cpu_data_var.set(str(cpu))
        gpu_data_var.set(str(gpu))
        print(f"\n【数据已更新】")
        print(f"CPU: {cpu}")
        print(f"GPU: {gpu}")


    # 初始数据（确保是10个点）
    init_cpu = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90]
    init_gpu = [0, 15, 25, 35, 45, 55, 65, 75, 85, 95]

    # 创建组件
    curve_widget = FanCurveWidget(root, cpu_data=init_cpu, gpu_data=init_gpu)
    curve_widget.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
    curve_widget.on_data_change = on_data_change

    # 初始化显示
    on_data_change({i * 10: init_cpu[i] for i in range(10)}, {i * 10: init_gpu[i] for i in range(10)})

    # 测试按钮框架
    btn_frame = ttk.Frame(root)
    btn_frame.pack(fill=tk.X, padx=8, pady=5)


    # 编辑状态控制函数
    def disable_editing():
        curve_widget.set_editable(False)
        edit_status_var.set("当前状态：曲线不可编辑（置灰显示）")
        edit_status_label.config(foreground="red")
        # messagebox.showinfo("状态提示", "已禁用编辑功能！\n折线图已置灰，无法拖拽编辑曲线。")


    def enable_editing():
        curve_widget.set_editable(True)
        edit_status_var.set("当前状态：曲线可编辑（彩色显示）")
        edit_status_label.config(foreground="green")
        # messagebox.showinfo("状态提示", "已启用编辑功能！\n折线图恢复彩色显示，可以拖拽编辑曲线。")


    def test_case1():
        # 不可编辑时无法修改数据
        if not curve_widget.editable:
            # messagebox.showwarning("操作提示", "编辑功能已禁用！无法修改数据，请先启用编辑。")
            return

        new_cpu = [0, 0, 10, 20, 30, 40, 50, 60, 70, 80]
        new_gpu = [0, 5, 15, 25, 35, 45, 55, 65, 75, 85]
        curve_widget.set_data(new_cpu, new_gpu)
        # messagebox.showinfo("测试提示", "已更新为递增数据！")


    def test_case2():
        # 不可编辑时无法修改数据
        if not curve_widget.editable:
            # messagebox.showwarning("操作提示", "编辑功能已禁用！无法修改数据，请先启用编辑。")
            return

        curve_widget.set_data(init_cpu, init_gpu)
        # messagebox.showinfo("测试提示", "已重置初始数据！")


    # 测试按钮
    ttk.Button(btn_frame, text="测试：递增数据", command=test_case1).pack(side=tk.LEFT, padx=4, pady=4)
    ttk.Button(btn_frame, text="重置初始数据", command=test_case2).pack(side=tk.LEFT, padx=4, pady=4)
    ttk.Button(btn_frame, text="禁用编辑（置灰）", command=disable_editing).pack(side=tk.LEFT, padx=4, pady=4)
    ttk.Button(btn_frame, text="启用编辑（恢复彩色）", command=enable_editing).pack(side=tk.LEFT, padx=4, pady=4)

    # 提示标签
    tip_label = ttk.Label(root, text="💡 已添加100℃刻度，90℃右侧可轻松拖拽 | 禁用编辑时图表自动置灰", font=("SimHei", 9),
                          foreground="blue")
    tip_label.pack(pady=5)

    # 启动主循环
    root.mainloop()