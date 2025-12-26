import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk, ImageEnhance
import shutil
import os


class BgWindowWithTransparency:
    def __init__(self, root):
        self.root = root
        self.root.title("背景图设置（支持透明度+自动拷贝）")
        self.root.geometry("800x600")  # 窗口初始尺寸

        # 背景图相关变量
        self.bg_image = None  # 原始背景图对象
        self.bg_image_transparent = None  # 带透明度的背景图对象
        self.bg_label = tk.Label(root)
        self.bg_label.place(x=0, y=0, relwidth=1, relheight=1)
        self.bg_label.lower()  # 背景图置于最底层

        # 透明度参数（0.0-1.0，1.0不透明，0.0完全透明）
        self.transparency = tk.DoubleVar(value=0.8)  # 默认80%不透明

        # 绑定窗口大小变化事件（核心：背景图跟随缩放）
        self.root.bind("<Configure>", self.on_window_resize)

        # 创建控制面板（主入口）
        # self.create_control_panel()

    def create_control_panel(self):
        """创建控制面板容器（统一管理控件）"""
        # 控制面板框架（防止控件被背景图遮挡）
        self.control_frame = tk.Frame(self.root, bg="white", padx=10, pady=10)
        self.control_frame.pack(pady=20, fill="x", padx=20)

        # 调用独立的控件创建方法
        self.create_bg_button()    # 创建背景图按钮
        self.create_transparency_slider()  # 创建透明度滑块

    def create_bg_button(self):
        """独立方法：创建选择背景图按钮"""
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

    def create_transparency_slider(self):
        """独立方法：创建透明度调节滑块"""
        # 滑块标签
        tk.Label(
            self.control_frame,
            text="背景透明度：",
            font=("微软雅黑", 10),
            bg="white"
        ).pack(side="left", padx=10)

        # 透明度滑块
        transparency_slider = tk.Scale(
            self.control_frame,
            variable=self.transparency,
            from_=0.0,
            to=1.0,
            resolution=0.05,  # 调节步长0.05
            orient="horizontal",
            length=200,
            command=self.update_bg_transparency  # 滑动时实时更新透明度
        )
        transparency_slider.pack(side="left", padx=10)

    def on_window_resize(self, event):
        """窗口大小变化时触发：重新缩放背景图"""
        # 避免窗口初始化时的无效触发
        if event.widget == self.root and self.bg_image is not None:
            self.update_bg_size()

    def update_bg_size(self):
        """更新背景图尺寸为当前窗口大小"""
        try:
            win_width = self.root.winfo_width()
            win_height = self.root.winfo_height()
            # 重新缩放背景图
            resized_bg = self.bg_image.resize(
                (win_width, win_height),
                Image.Resampling.LANCZOS
            )
            # 重新应用透明度
            self.bg_image = resized_bg
            self.update_bg_transparency(self.transparency.get())
        except Exception as e:
            print(f"缩放背景图失败：{str(e)}")

    def choose_and_copy_bg(self):
        """选择背景图 → 拷贝到当前文件夹（统一命名为background）→ 设置为窗口背景"""
        # 1. 打开文件选择对话框
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
            # 2. 拷贝图片到当前文件夹（统一命名为background，保留原扩展名）
            current_dir = os.getcwd()
            file_ext = os.path.splitext(file_path)[1]
            target_name = f"background{file_ext}"
            target_path = os.path.join(current_dir, target_name)

            # 直接覆盖，不提示
            shutil.copy2(file_path, target_path)  # 保留文件元数据

            # 3. 加载图片并设置背景（带透明度）
            self.load_bg_image(target_path)

        except PermissionError:
            print("错误", "权限不足，无法写入图片到当前文件夹！")
        except Exception as e:
            print("错误", f"操作失败：{str(e)}")

    def load_bg_image(self, image_path):
        """加载图片并应用初始透明度"""
        try:
            # 检查文件是否存在
            if not os.path.exists(image_path):
                raise FileNotFoundError(f"图片文件不存在：{image_path}")

            # 打开图片（保留原始尺寸，不直接缩放）
            self.bg_image = Image.open(image_path)
            # 初始缩放为窗口大小
            self.update_bg_size()

        except Exception as e:
            messagebox.showerror("错误", f"加载图片失败：{str(e)}")

    def update_bg_transparency(self, value):
        """实时更新背景图透明度"""
        if self.bg_image is None:
            return

        try:
            # 将透明度值转为浮点数
            alpha = float(value)
            # 创建带透明度的图片副本
            img_with_alpha = self.bg_image.copy()

            # 处理RGBA（透明通道）
            if img_with_alpha.mode != 'RGBA':
                img_with_alpha = img_with_alpha.convert('RGBA')

            # 调整整体透明度
            alpha_channel = img_with_alpha.split()[3]  # 获取Alpha通道
            alpha_channel = ImageEnhance.Brightness(alpha_channel).enhance(alpha)
            img_with_alpha.putalpha(alpha_channel)

            # 转换为Tkinter可用格式
            self.bg_image_transparent = ImageTk.PhotoImage(img_with_alpha)
            self.bg_label.config(image=self.bg_image_transparent)
        except Exception as e:
            messagebox.showerror("错误", f"调整透明度失败：{str(e)}")


if __name__ == "__main__":
    root = tk.Tk()
    app = BgWindowWithTransparency(root)
    # 延迟加载背景图（等窗口初始化完成）
    root.after(50, lambda: app.load_bg_image("background.png"))
    root.mainloop()