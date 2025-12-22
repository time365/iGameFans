import tkinter as tk
import tkinter.ttk as ttk
from tkinter import colorchooser
from typing import Optional, Callable, Union  # 兼容低版本Python的类型注解


class ColorConverter:
    # ========== 工具函数：RGB 转 TK 十六进制颜色 ==========
    @staticmethod
    def rgb_to_tk_color(rgb: tuple) -> str:
        """将 (R, G, B) 转换为 TK 兼容的 #RRGGBB 格式"""
        return "#{:02x}{:02x}{:02x}".format(rgb[0], rgb[1], rgb[2])  # 兼容所有Python版本的格式化

    # ========== 工具函数：十六进制颜色转RGB ==========
    @staticmethod
    def tk_color_to_rgb(tk_color: str) -> tuple:
        """将 #RRGGBB 格式转换为 (R, G, B) 元组"""
        tk_color = tk_color.lstrip('#')
        return (
            int(tk_color[0:2], 16),
            int(tk_color[2:4], 16),
            int(tk_color[4:6], 16)
        )


# ========== 工具函数：获取组件的顶级窗口 ==========
def get_top_window(widget: tk.Widget) -> Union[tk.Tk, tk.Toplevel]:
    """递归获取组件所属的顶级窗口（Tk/Toplevel），兼容任意嵌套层级"""
    parent = widget.master
    while not isinstance(parent, (tk.Tk, tk.Toplevel)):
        parent = parent.master
    return parent


# ========== 自定义颜色选择器（全平台兼容版） ==========
class ColorChooserWidget(ttk.Frame):
    """自定义颜色选择器：显示颜色块 + 打开系统颜色选择器（兼容Windows/macOS/Linux）"""

    def __init__(self, parent, default_color: str = "#ff0000",
                 command: Optional[Callable] = None, **kwargs):
        super().__init__(parent, **kwargs)
        self.parent = parent  # 直接父组件（可能是Frame）
        self.top_window = get_top_window(parent)  # 顶级窗口（Tk/Toplevel）
        self.selected_color = default_color  # 选中的颜色（十六进制格式）
        self.command = command  # 自定义选中回调（可选）

        # 1. 颜色块 Canvas（显示当前选中的颜色）
        self.color_canvas = tk.Canvas(
            self,
            width=20,
            height=20,
            bg=self.selected_color,
            highlightthickness=1,
            highlightbackground="gray"
        )
        self.color_canvas.pack(side=tk.LEFT, padx=(0, 5))
        # 绘制边框（避免Canvas样式问题）
        self.color_canvas.create_rectangle(
            1, 1, 19, 19,
            outline="black",
            width=1
        )

        # 2. 颜色选择按钮（点击打开colorchooser）
        self.choose_btn = ttk.Button(
            self,
            text="选择颜色",
            width=10,
            command=self._open_color_chooser,
            style="Toolbutton"
        )
        self.choose_btn.pack(side=tk.RIGHT, fill=tk.X, expand=True)

        # 3. 绑定颜色块点击事件（也可打开颜色选择器）
        self.color_canvas.bind("<Button-1>", lambda e: self._open_color_chooser())

    def _open_color_chooser(self):
        """打开系统颜色选择器并更新选中颜色（全平台兼容，无activate报错）"""
        # 核心兼容方案：仅使用全平台支持的方法
        # 1. 将顶级窗口提到最前（全平台支持）
        self.top_window.lift()
        # 2. 临时置顶顶级窗口（防止被调色板遮挡/最小化）
        self.top_window.attributes('-topmost', True)

        try:
            # 打开颜色选择器，指定顶级窗口为父窗口（关键：避免窗口层级错乱）
            result = colorchooser.askcolor(
                color=self.selected_color,
                title="选择颜色",
                parent=self.top_window
            )

            # 用户点击取消时返回 (None, None)，直接返回
            if result[0] is None or result[1] is None:
                return

            # 更新选中颜色（十六进制格式）
            self.selected_color = result[1]

            # 更新颜色块显示
            self.color_canvas.config(bg=self.selected_color)
            # 重新绘制边框（避免颜色更新后边框消失）
            self.color_canvas.delete("all")
            self.color_canvas.create_rectangle(
                1, 1, 19, 19,
                outline="black",
                width=1
            )

            # 执行自定义回调
            if self.command is not None and callable(self.command):
                self.command()
        finally:
            # 恢复窗口属性：取消置顶（避免一直置顶影响操作）
            self.top_window.attributes('-topmost', False)
            # 再次将窗口提到最前（确保调色板关闭后窗口可见）
            self.top_window.lift()
            # 强制刷新窗口（解决部分系统窗口未及时显示的问题）
            self.top_window.update()

    def get_selected(self) -> str:
        """获取选中的颜色（十六进制格式，如 #ff0000）"""
        return self.selected_color

    def get_selected_rgb(self) -> tuple:
        """获取选中颜色的RGB值（如 (255, 0, 0)）"""
        return ColorConverter.tk_color_to_rgb(self.selected_color)

    def set_color(self, color: str):
        """手动设置颜色（支持十六进制格式）"""
        self.selected_color = color
        self.color_canvas.config(bg=self.selected_color)
        self.color_canvas.delete("all")
        self.color_canvas.create_rectangle(
            1, 1, 19, 19,
            outline="black",
            width=1
        )


# ========== 使用示例 ==========
if __name__ == "__main__":
    root = tk.Tk()
    root.title("ColorChooser 颜色选择器示例")
    root.geometry("300x100")


    # 自定义选中后的回调函数
    def on_color_selected():
        """颜色选择后的额外逻辑"""
        selected_hex = color_widget.get_selected()
        selected_rgb = color_widget.get_selected_rgb()
        print(f"自定义回调：选中颜色（十六进制）：{selected_hex} | RGB：{selected_rgb}")


    # 创建主框架
    frame = ttk.Frame(root, padding=20)
    frame.pack(fill=tk.BOTH, expand=True)

    # 添加标签
    ttk.Label(frame, text="键盘颜色:").pack(side=tk.LEFT, padx=5)

    # 创建自定义颜色选择器（默认红色 #ff0000）
    color_widget = ColorChooserWidget(
        frame,
        default_color="#ff0000",
        command=on_color_selected
    )
    color_widget.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)


    # 测试获取选中值的按钮
    def get_selected_color():
        selected_hex = color_widget.get_selected()
        selected_rgb = color_widget.get_selected_rgb()
        print(f"\n选中颜色：")
        print(f"十六进制：{selected_hex}")
        print(f"RGB：{selected_rgb}")


    ttk.Button(frame, text="获取选中值", command=get_selected_color).pack(side=tk.LEFT, padx=5)

    root.mainloop()