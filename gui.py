import sys
import os
import threading
import tkinter as tk
from tkinter import messagebox, filedialog

# ───────────────── ttkbootstrap 主题 ─────────────────
try:
    import ttkbootstrap as ttk
    from ttkbootstrap.constants import *
    THEME = "darkly"
    USE_BOOTSTRAP = True
except ImportError:
    import tkinter.ttk as ttk
    THEME = None
    USE_BOOTSTRAP = False
    print("⚠️ ttkbootstrap 未安装，使用默认 Tkinter 样式。可通过 `pip install ttkbootstrap` 安装获得更好效果。")

# ────────────── 拖拽支持（可选） ──────────────
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DRAG_SUPPORT = True
except ImportError:
    DRAG_SUPPORT = False
    print("⚠️ tkinterdnd2 未安装，拖拽功能不可用。可通过 `pip install tkinterdnd2` 启用。")

# 导入核心处理模块
from auto_patch import process_apk, setup_java, resource_path

# 初始化内嵌 Java 环境（auto_patch 模块已自动调用，但这里显式调用一次也无害）
java_exe = setup_java()


class RedirectText:
    def __init__(self, text_widget):
        self.text_widget = text_widget

    def write(self, string):
        self.text_widget.insert(tk.END, string)
        self.text_widget.see(tk.END)
        self.text_widget.update_idletasks()

    def flush(self):
        pass


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("maapvz 免绑小助手")
        self.root.geometry("700x600")
        self.root.minsize(550, 450)

        try:
            icon_path = resource_path("icon.ico")
            if os.path.exists(icon_path):
                self.root.iconbitmap(icon_path)
        except:
            pass

        self.apk_path = None
        self.create_widgets()
        self.redirect_stdout()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def on_close(self):
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
        self.root.destroy()

    def create_widgets(self):
        main = ttk.Frame(self.root, padding=15)
        main.pack(fill=tk.BOTH, expand=True)

        # 标题
        title_kwargs = {"font": ("Microsoft YaHei", 16, "bold")}
        if USE_BOOTSTRAP:
            title_kwargs["bootstyle"] = PRIMARY
        title = ttk.Label(main, text="🌻 植物大战僵尸2 免绑小助手", **title_kwargs)
        title.pack(pady=(0, 10))

        # 拖拽区域
        drop_kwargs = {"height": 120, "relief": "solid", "borderwidth": 1}
        if USE_BOOTSTRAP:
            drop_kwargs["bootstyle"] = "light"
        self.drop_frame = ttk.Frame(main, **drop_kwargs)
        self.drop_frame.pack(fill=tk.X, padx=5, pady=5)
        self.drop_frame.pack_propagate(False)

        self.file_label = ttk.Label(
            self.drop_frame,
            text="📂 拖拽 APK 文件到此处\n或点击下方按钮选择文件",
            anchor="center",
            font=("Microsoft YaHei", 10),
            justify="center"
        )
        self.file_label.pack(expand=True)

        if DRAG_SUPPORT:
            self.drop_frame.drop_target_register(DND_FILES)
            self.drop_frame.dnd_bind('<<Drop>>', self.on_drop)

        # 按钮行
        btn_frame = ttk.Frame(main)
        btn_frame.pack(pady=10)

        choose_kwargs = {"text": "📁 选择 APK", "command": self.choose_file}
        if USE_BOOTSTRAP:
            choose_kwargs["bootstyle"] = "info-outline"
        self.choose_btn = ttk.Button(btn_frame, **choose_kwargs)
        self.choose_btn.pack(side=tk.LEFT, padx=5)

        start_kwargs = {"text": "🚀 开始免绑", "command": self.start_process, "state": "disabled"}
        if USE_BOOTSTRAP:
            start_kwargs["bootstyle"] = "success"
        self.start_btn = ttk.Button(btn_frame, **start_kwargs)
        self.start_btn.pack(side=tk.LEFT, padx=5)

        # 进度条
        progress_kwargs = {"mode": "indeterminate"}
        if USE_BOOTSTRAP:
            progress_kwargs["bootstyle"] = "info-striped"
        self.progress = ttk.Progressbar(main, **progress_kwargs)

        # 日志区域
        log_frame = ttk.Frame(main)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        self.log_text = tk.Text(
            log_frame,
            wrap="word",
            height=10,
            font=("Consolas", 9),
            bg="#2b2b2b",
            fg="#dcdcdc",
            insertbackground="white",
            relief="flat",
            borderwidth=0,
            padx=5,
            pady=5
        )
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def redirect_stdout(self):
        sys.stdout = RedirectText(self.log_text)
        sys.stderr = RedirectText(self.log_text)

    def on_drop(self, event):
        files = self.root.tk.splitlist(event.data)
        if files:
            path = files[0].strip('{}')
            if path.lower().endswith('.apk'):
                self.apk_path = path
                self.file_label.config(text=f"📦 已选择:\n{os.path.basename(path)}")
                self.start_btn.config(state="normal")
            else:
                messagebox.showerror("错误", "请拖入 .apk 文件")

    def choose_file(self):
        path = filedialog.askopenfilename(
            title="选择 APK 文件",
            filetypes=[("APK files", "*.apk"), ("All files", "*.*")]
        )
        if path:
            self.apk_path = path
            self.file_label.config(text=f"📦 已选择:\n{os.path.basename(path)}")
            self.start_btn.config(state="normal")

    def start_process(self):
        if not self.apk_path:
            return
        self.start_btn.config(state="disabled")
        self.choose_btn.config(state="disabled")
        self.log_text.delete(1.0, tk.END)
        self.progress.pack(fill=tk.X, padx=5, pady=5)
        self.progress.start(10)
        print(f"开始处理: {self.apk_path}\n")
        threading.Thread(target=self.run_process, daemon=True).start()

    def run_process(self):
        try:
            result = process_apk(self.apk_path)
            print(f"\n✅ 免绑成功！\n输出文件: {result}")
            self.root.after(0, lambda: messagebox.showinfo(
                "成功", f"免绑包已生成:\n{result}\n\n可以关闭本窗口或继续处理其他APK。"))
        except Exception as ex:
            error_msg = str(ex)   # 避免作用域问题
            print(f"\n❌ 处理失败: {error_msg}")
            self.root.after(0, lambda: messagebox.showerror("错误", error_msg))
        finally:
            self.root.after(0, self.reset_ui)

    def reset_ui(self):
        self.progress.stop()
        self.progress.pack_forget()
        self.start_btn.config(state="normal")
        self.choose_btn.config(state="normal")
        self.file_label.config(text="📂 拖拽 APK 文件到此处\n或点击下方按钮选择文件")
        self.apk_path = None


if __name__ == "__main__":
    if DRAG_SUPPORT:
        root = TkinterDnD.Tk()
    elif USE_BOOTSTRAP:
        root = ttk.Window(themename=THEME)
    else:
        root = tk.Tk()

    app = App(root)
    root.mainloop()