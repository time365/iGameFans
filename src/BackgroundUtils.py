import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk, ImageEnhance
import shutil
import os


class BackgroundImageComponent:
    """
    背景图独立组件（支持外部传参、自适应缩放、透明度调节）
    :param master: 父容器（tk.Tk/tk.Frame）
    :param bg_image_path: 初始背景图路径（外部传入）
    :param init_transparency: 初始透明度（0.0-1.0，外部传入）
    """

    def __init__(self, master, bg_image_path="", init_transparency=0.8):
        # 父容器
        self.master = master

        # 外部传入参数
        self.bg_image_path = bg_image_path  # 初始背景图路径
        self.init_transparency = init_transparency  # 初始透明度

        # 背景图核心变量
        self.bg_original = None  # 原始背景图（未缩放）
        self.bg_image = None  # 缩放后的背景图
        self.bg_image_transparent = None  # 带透明度的背景图
        self.bg_label = tk.Label(master,bd=0, highlightthickness=0)
        self.bg_label.place(x=0, y=0, relwidth=1, relheight=1)
        self.bg_label.lower()  # 置于最底层

        # 透明度变量（使用外部传入的初始值）
        self.transparency = tk.DoubleVar(value=self.init_transparency)

        # 绑定窗口缩放事件（自适应）
        self.master.bind("<Configure>", self.on_window_resize)

        # 初始化：加载初始背景图（如果路径有效）
        if self.bg_image_path and os.path.exists(self.bg_image_path):
            self.load_bg_image(self.bg_image_path)

    def create_control_widgets(self, parent_frame=None):
        """
        创建控制面板（按钮+滑块），支持指定父容器（外部灵活布局）
        :param parent_frame: 控件父容器（默认创建独立Frame）
        """
        # 若未指定父容器，自动创建一个
        if parent_frame is None:
            self.control_frame = tk.Frame(self.master, bg="white", padx=10, pady=10)
            self.control_frame.pack(pady=20, fill="x", padx=20)
        else:
            self.control_frame = parent_frame

        # 创建子控件（拆分为独立方法）
        self._create_bg_select_button()
        self._create_transparency_slider()

    def _create_bg_select_button(self):
        """创建选择背景图按钮（内部方法）"""
        bg_btn = tk.Button(
            self.control_frame,
            text="选择并设置背景图",
            command=self.choose_and_copy_bg,
            font=("微软雅黑", 12),
            bg="#165DFF",
            fg="white",
            padx=20,
            pady=8,
            relief="flat"
        )
        bg_btn.pack(side="left", padx=10)

    def _create_transparency_slider(self):
        """创建透明度滑块（内部方法）"""
        # 滑块标签
        tk.Label(
            self.control_frame,
            text="背景透明度：",
            font=("微软雅黑", 10),
            bg="white"
        ).pack(side="left", padx=10)

        # 透明度滑块（使用外部传入的初始值）
        transparency_slider = tk.Scale(
            self.control_frame,
            variable=self.transparency,
            from_=0.0,
            to=1.0,
            resolution=0.05,
            orient="horizontal",
            length=200,
            command=self.update_bg_transparency
        )
        transparency_slider.pack(side="left", padx=10)

    def choose_and_copy_bg(self):
        """选择图片 → 拷贝到当前目录（统一命名）→ 加载"""
        file_path = filedialog.askopenfilename(
            title="选择背景图片",
            filetypes=[
                ("图片文件", "*.png *.jpg *.jpeg *.bmp *.gif"),
                ("所有文件", "*.*")
            ]
        )
        if not file_path:
            return

        try:
            # 拷贝到当前目录，统一命名为background+原扩展名
            current_dir = os.getcwd()
            file_ext = os.path.splitext(file_path)[1]
            target_path = os.path.join(current_dir, f"background{file_ext}")
            shutil.copy2(file_path, target_path)  # 直接覆盖

            # 更新当前背景图路径并加载
            self.bg_image_path = target_path
            self.load_bg_image(target_path)

        except PermissionError:
            messagebox.showerror("错误", "权限不足，无法写入图片到当前文件夹！")
        except Exception as e:
            messagebox.showerror("错误", f"拷贝图片失败：{str(e)}")

    def load_bg_image(self, image_path):
        """加载背景图（外部可调用）"""
        try:
            if not os.path.exists(image_path):
                raise FileNotFoundError(f"图片不存在：{image_path}")

            # 保存原始图片（用于缩放）
            self.bg_original = Image.open(image_path)
            print(f"原始图片尺寸：{self.bg_original.size}")
            # 初始缩放到窗口大小
            self.update_bg_size()

        except Exception as e:
            messagebox.showerror("错误", f"加载背景图失败：{str(e)}")

    def update_bg_size(self):
        """更新背景图尺寸（自适应窗口）"""
        if self.bg_original is None:
            return

        try:
            # 获取当前父容器尺寸
            win_width = self.master.winfo_width()
            win_height = self.master.winfo_height()
            # 避免初始化时尺寸异常
            win_width = win_width if win_width > 0 else 800
            win_height = win_height if win_height > 0 else 600

            # 缩放图片
            self.bg_image = self.bg_original.resize(
                (win_width, win_height),
                Image.Resampling.LANCZOS
            )
            # 应用当前透明度
            self.update_bg_transparency(self.transparency.get())

        except Exception as e:
            print(f"缩放背景图失败：{str(e)}")

    def update_bg_transparency(self, value):
        """更新背景图透明度（外部可调用）"""
        if self.bg_image is None:
            return

        try:
            alpha = float(value)
            img_with_alpha = self.bg_image.copy()

            # 处理透明通道
            if img_with_alpha.mode != 'RGBA':
                img_with_alpha = img_with_alpha.convert('RGBA')

            # 调整透明度
            alpha_channel = img_with_alpha.split()[3]
            alpha_channel = ImageEnhance.Brightness(alpha_channel).enhance(alpha)
            img_with_alpha.putalpha(alpha_channel)

            # 更新背景
            self.bg_image_transparent = ImageTk.PhotoImage(img_with_alpha)
            self.bg_label.config(image=self.bg_image_transparent)

        except Exception as e:
            messagebox.showerror("错误", f"调整透明度失败：{str(e)}")

    def on_window_resize(self, event):
        """窗口缩放事件回调"""
        if event.widget == self.master and self.bg_original is not None:
            self.update_bg_size()

    def get_current_transparency(self):
        """获取当前透明度（供外部读取）"""
        return self.transparency.get()

    def set_transparency(self, value):
        """设置透明度（供外部调用）"""
        if 0.0 <= value <= 1.0:
            self.transparency.set(value)
            self.update_bg_transparency(value)


# ===================== 测试使用示例 =====================
if __name__ == "__main__":
    # 主窗口
    root = tk.Tk()
    root.title("背景图独立组件测试")
    root.geometry("800x600")

    # 1. 外部传入参数
    custom_bg_path = "./asset/background.png"  # 自定义图片路径
    custom_transparency = 0.7  # 自定义初始透明度

    # 2. 创建独立组件（传入参数）
    bg_component = BackgroundImageComponent(
        master=root,
        bg_image_path=custom_bg_path,
        init_transparency=custom_transparency
    )

    # 3. 创建控制面板（可指定父容器，灵活布局）
    bg_component.create_control_widgets()


    # 4. 外部控制示例（可选）
    # 比如：按钮点击修改透明度
    def set_custom_alpha():
        bg_component.set_transparency(0.5)


    tk.Button(
        root,
        text="设置透明度为50%",
        command=set_custom_alpha
    ).pack(side="bottom", pady=20)

    root.mainloop()