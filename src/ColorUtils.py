import tkinter as tk
import tkinter.ttk as ttk
from typing import List, Optional, Callable

# ========== 颜色字典（替换原有枚举类） ==========
Color = {
    "DBlue": (113, 226, 209),  # Default Blue
    "White": (255, 255, 255),  # White
    "Red": (255, 0, 0),  # Red
    "Orange": (255, 165, 35),  # Orange
    "Yellow": (255, 255, 0),  # Yellow
    "YGreen": (173, 255, 194),  # YellowGreen
    "Green": (0, 200, 0),  # Green
    "Blue": (0, 0, 255),  # Blue
    "Violet": (255, 20, 255),  # Violet
    "Purple": (128, 0, 128),  # Purple
    "Pink": (255, 20, 147)  # Pink
}

# 定义颜色名称类型（方便类型提示）
ColorName = str


# ========== 工具函数：RGB 转 TK 十六进制颜色 ==========
def rgb_to_tk_color(rgb: tuple) -> str:
    """将 (R, G, B) 转换为 TK 兼容的 #RRGGBB 格式"""
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


# ========== 自定义带颜色块的下拉框（适配字典） ==========
class ColorCombobox(ttk.Frame):
    """自定义下拉框：显示颜色块+颜色名称（适配颜色字典）"""
    # 可选：如果需要自定义选中后的额外回调，保留command参数并标注类型
    def __init__(self, parent, color_names: List[ColorName], textvariable: tk.StringVar,
                 command: Optional[Callable] = None, **kwargs):
        super().__init__(parent, **kwargs)
        self.color_names = color_names  # 颜色名称列表（对应Color字典的key）
        self.selected_color: Optional[ColorName] = None  # 选中的颜色名称
        self.command = command  # 自定义选中回调（可选）

        # 1. 下拉框（显示颜色名称，如 "DBlue"）
        self.var = textvariable
        self.combobox = ttk.Combobox(
            self,
            textvariable=self.var,
            width=10,  # 缩小宽度适配左侧布局
            state="readonly",
            font=("微软雅黑", 10)
            # 移除错误的 command 参数！ttk.Combobox 不支持该参数
        )
        self.combobox.pack(side=tk.RIGHT, fill=tk.X, expand=True)
        # 绑定选中事件（核心：通过事件绑定实现选中回调）
        self.combobox.bind("<<ComboboxSelected>>", self._on_select)

        # 2. 初始化下拉框选项 + 设置默认选中项（核心修改）
        self._refresh_options()

        # 3. 颜色块 Canvas（绘制选中的颜色）
        # 优先使用textvariable的默认值初始化颜色块
        default_color_name = self.var.get()
        # 兜底：如果默认值不在列表中，选第一个
        if default_color_name not in self.color_names and self.color_names:
            default_color_name = self.color_names[0]
            self.var.set(default_color_name)

        tk_color = rgb_to_tk_color(Color[default_color_name])

        self.color_canvas = tk.Canvas(
            self,
            width=20,
            height=20,
            bg=tk_color,
            highlightthickness=1,
            highlightbackground="gray"  # 边框颜色
        )
        self.color_canvas.pack(side=tk.LEFT, padx=(0, 5))

        # 初始化选中状态和颜色块边框
        self.selected_color = default_color_name
        self.color_canvas.create_rectangle(
            1, 1, 19, 19,
            outline="black",
            width=1
        )

    def _refresh_options(self):
        """刷新下拉框选项（颜色名称列表）"""
        # 设置下拉框值为颜色名称列表
        self.combobox["values"] = self.color_names

        # 核心修改：优先选中textvariable的默认值，而非第一个
        default_val = self.var.get()
        if default_val in self.color_names:
            # 找到默认值在列表中的索引并选中
            idx = self.color_names.index(default_val)
            self.combobox.current(idx)
        elif self.color_names:
            # 兜底：默认值无效时选第一个
            self.combobox.current(0)
            self.var.set(self.color_names[0])

    def _on_select(self, event):
        """选中选项后更新颜色块和选中状态 + 执行自定义回调"""
        selected_name = self.var.get()
        if not selected_name or selected_name not in self.color_names:
            return

        # 更新选中状态
        self.selected_color = selected_name

        # 获取对应的RGB值并更新颜色块
        tk_color = rgb_to_tk_color(Color[selected_name])
        # 更新颜色块背景
        self.color_canvas.config(bg=tk_color)
        # 清空原有绘制（避免多重边框）
        self.color_canvas.delete("all")
        # 绘制黑色边框增强视觉
        self.color_canvas.create_rectangle(
            1, 1, 19, 19,
            outline="black",
            width=1
        )

        # 可选：执行自定义回调（如果传入了command）
        if self.command is not None and callable(self.command):
            self.command()  # 可按需传参，比如 self.command(selected_name)

    def update_color_list(self, new_color_names: List[ColorName]):
        """更新颜色名称列表并刷新下拉框"""
        self.color_names = new_color_names
        self._refresh_options()
        # 刷新颜色块
        self._on_select(None)

    def get_selected(self) -> Optional[ColorName]:
        """获取选中的颜色名称"""
        return self.selected_color

    def get_selected_rgb(self) -> Optional[tuple]:
        """获取选中颜色的RGB值"""
        if self.selected_color and self.selected_color in Color:
            return Color[self.selected_color]
        return None


# ========== 使用示例（集成到原有布局） ==========
if __name__ == "__main__":
    root = tk.Tk()
    root.title("颜色下拉框示例")
    root.geometry("300x100")

    # 可选：自定义选中后的回调函数
    def on_color_selected():
        """下拉框选中后的额外逻辑"""
        selected = kl_color_combo.get_selected()
        print(f"自定义回调：选中了 {selected}")

    # 2. 创建自定义颜色下拉框（替换原有Combobox）
    frame = ttk.Frame(root, padding=20)
    frame.pack(fill=tk.BOTH, expand=True)

    # 键盘灯光颜色选择：传入默认值"Red"
    ttk.Label(frame, text="键盘颜色:").pack(side=tk.LEFT, padx=5)
    kl_color_var = tk.StringVar(value="Red")  # 显式定义变量（方便后续修改）
    kl_color_combo = ColorCombobox(
        frame,
        color_names=list(Color.keys()),
        textvariable=kl_color_var,
        command=on_color_selected  # 传入自定义回调（可选）
        # 如果不需要自定义回调，直接删除 command 参数即可
    )
    kl_color_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

    # 3. 测试获取选中值
    def get_selected_color():
        selected_name = kl_color_combo.get_selected()
        selected_rgb = kl_color_combo.get_selected_rgb()
        if selected_name and selected_rgb:
            print(f"选中颜色：{selected_name} | RGB：{selected_rgb}")

    ttk.Button(frame, text="获取选中值", command=get_selected_color).pack(side=tk.LEFT, padx=5)

    root.mainloop()