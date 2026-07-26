import sys
import os
import threading
import tkinter as tk
from tkinter import messagebox, filedialog

# ────────────── 高级 UI 库 ──────────────
try:
    import customtkinter as ctk
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")
    USE_CTK = True
except ImportError:
    import tkinter as ctk_fallback
    USE_CTK = False
    print("⚠️ customtkinter 未安装，使用默认 Tkinter 样式。可通过 `pip install customtkinter` 安装获得更好效果。")

# ────────────── 拖拽支持 ──────────────
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DRAG_SUPPORT = True
except ImportError:
    DRAG_SUPPORT = False
    print("⚠️ tkinterdnd2 未安装，拖拽功能不可用。可通过 `pip install tkinterdnd2` 启用。")

from auto_patch import process_apk, setup_java, resource_path

# 初始化内嵌 Java
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
        self.root.geometry("750x660")
        self.root.minsize(650, 550)

        # 半透明效果
        try:
            self.root.attributes('-alpha', 0.97)
        except:
            pass

        # 图标
        try:
            icon_path = resource_path("icon.ico")
            if os.path.exists(icon_path):
                self.root.iconbitmap(icon_path)
        except:
            pass

        self.apk_path = None
        self.use_ctk = USE_CTK

        # 发光动画控制
        self._glow_step = 0
        self._glow_colors = ["#3b3b3b", "#4a9eff", "#3b3b3b"]

        self.create_widgets()
        self.redirect_stdout()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        if DRAG_SUPPORT and self.use_ctk:
            self.start_glow_animation()

    def on_close(self):
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
        self.root.destroy()

    def create_widgets(self):
        # 主容器
        main = ctk.CTkFrame(self.root, corner_radius=15, fg_color="#1a1a1a") if self.use_ctk else tk.Frame(self.root, bg="#1a1a1a")
        main.pack(fill="both", expand=True, padx=10, pady=10)

        # 标题
        title_font = ctk.CTkFont(family="Microsoft YaHei", size=20, weight="bold") if self.use_ctk else ("Microsoft YaHei", 20, "bold")
        if self.use_ctk:
            self.title_label = ctk.CTkLabel(main, text="🌻 植物大战僵尸2 免绑小助手", font=title_font, text_color="#4a9eff")
        else:
            self.title_label = tk.Label(main, text="🌻 植物大战僵尸2 免绑小助手", font=title_font, fg="#4a9eff", bg="#1a1a1a")
        self.title_label.pack(pady=(15, 10))

        # 拖拽区域
        self.drop_frame = ctk.CTkFrame(main, corner_radius=10, border_width=2, fg_color="transparent", border_color="#3b3b3b") if self.use_ctk else tk.Frame(main, bg="#2b2b2b", relief="groove", bd=2)
        self.drop_frame.pack(fill="x", padx=20, pady=10, ipady=35)

        self.file_label = ctk.CTkLabel(
            self.drop_frame,
            text="📂 拖拽 APK 文件到此处\n或点击下方按钮选择文件",
            font=ctk.CTkFont(family="Microsoft YaHei", size=12) if self.use_ctk else ("Microsoft YaHei", 12),
            justify="center",
            text_color="#aaaaaa"
        ) if self.use_ctk else tk.Label(self.drop_frame, text="📂 拖拽 APK 文件到此处\n或点击下方按钮选择文件", font=("Microsoft YaHei", 12), fg="#aaaaaa", bg="#2b2b2b")
        self.file_label.pack(expand=True)

        if DRAG_SUPPORT:
            if self.use_ctk:
                self.drop_frame.drop_target_register(DND_FILES)
                self.drop_frame.dnd_bind('<<Drop>>', self.on_drop)
            else:
                self.root.drop_target_register(DND_FILES)
                self.root.dnd_bind('<<Drop>>', self.on_drop)

        # 按钮行
        btn_frame = ctk.CTkFrame(main, fg_color="transparent") if self.use_ctk else tk.Frame(main, bg="#1a1a1a")
        btn_frame.pack(pady=15)

        # 选择按钮
        self.choose_btn = ctk.CTkButton(
            btn_frame,
            text="📁 选择 APK",
            command=self.choose_file,
            width=160,
            height=40,
            corner_radius=8,
            fg_color="#2b5b84",
            hover_color="#1e405e",
            font=ctk.CTkFont(size=14, weight="bold")
        ) if self.use_ctk else tk.Button(btn_frame, text="📁 选择 APK", command=self.choose_file, width=15)
        self.choose_btn.pack(side="left", padx=10)

        # 开始按钮
        self.start_btn = ctk.CTkButton(
            btn_frame,
            text="🚀 开始免绑",
            command=self.start_process,
            state="disabled",
            width=160,
            height=40,
            corner_radius=8,
            fg_color="#2b7a4b",
            hover_color="#1e5a37",
            font=ctk.CTkFont(size=14, weight="bold")
        ) if self.use_ctk else tk.Button(btn_frame, text="🚀 开始免绑", command=self.start_process, state="disabled", width=15)
        self.start_btn.pack(side="left", padx=10)

        # 进度条
        self.progress = ctk.CTkProgressBar(main, height=8, corner_radius=4, progress_color="#4a9eff") if self.use_ctk else tk.ttk.Progressbar(main, mode="indeterminate")
        self.progress.pack_forget()

        # 日志区域
        log_frame = ctk.CTkFrame(main, corner_radius=10, fg_color="#1e1e1e") if self.use_ctk else tk.Frame(main, bg="#1e1e1e")
        log_frame.pack(fill="both", expand=True, padx=20, pady=(15, 10))

        if self.use_ctk:
            self.log_text = ctk.CTkTextbox(
                log_frame,
                font=("Consolas", 11),
                fg_color="#1e1e1e",
                text_color="#dcdcdc",
                corner_radius=8,
                wrap="word"
            )
        else:
            self.log_text = tk.Text(
                log_frame,
                wrap="word",
                height=10,
                font=("Consolas", 11),
                bg="#1e1e1e",
                fg="#dcdcdc",
                insertbackground="white",
                relief="flat",
                borderwidth=0,
                padx=15,
                pady=15
            )
        self.log_text.pack(fill="both", expand=True, padx=5, pady=5)

        # 状态栏
        status_text = f"v2.0 | Java: {'内嵌' if java_exe != 'java' else '系统'}"
        if self.use_ctk:
            self.status_label = ctk.CTkLabel(main, text=status_text, font=("Microsoft YaHei", 10), text_color="#888888")
        else:
            self.status_label = tk.Label(main, text=status_text, font=("Microsoft YaHei", 10), fg="#888888", bg="#1a1a1a")
        self.status_label.pack(anchor="e", padx=20, pady=(0, 10))

    def start_glow_animation(self):
        def animate():
            color = self._glow_colors[self._glow_step % len(self._glow_colors)]
            try:
                self.drop_frame.configure(border_color=color)
            except:
                pass
            self._glow_step += 1
            self.root.after(2000, animate)
        animate()

    def redirect_stdout(self):
        sys.stdout = RedirectText(self.log_text)
        sys.stderr = RedirectText(self.log_text)

    def on_drop(self, event):
        files = self.root.tk.splitlist(event.data)
        if files:
            path = files[0].strip('{}')
            if path.lower().endswith('.apk'):
                self.apk_path = path
                self.file_label.configure(text=f"📦 已选择:\n{os.path.basename(path)}")
                self.start_btn.configure(state="normal")
            else:
                messagebox.showerror("错误", "请拖入 .apk 文件")

    def choose_file(self):
        path = filedialog.askopenfilename(
            title="选择 APK 文件",
            filetypes=[("APK files", "*.apk"), ("All files", "*.*")]
        )
        if path:
            self.apk_path = path
            self.file_label.configure(text=f"📦 已选择:\n{os.path.basename(path)}")
            self.start_btn.configure(state="normal")

    def start_process(self):
        if not self.apk_path:
            return
        self.start_btn.configure(state="disabled")
        self.choose_btn.configure(state="disabled")
        self.log_text.delete("1.0", "end")
        self.progress.pack(fill="x", padx=20, pady=5)
        self.progress.start()
        print(f"开始处理: {self.apk_path}\n")
        threading.Thread(target=self.run_process, daemon=True).start()

    def run_process(self):
        try:
            result = process_apk(self.apk_path)
            print(f"\n✅ 免绑成功！\n输出文件: {result}")
            self.root.after(0, lambda: messagebox.showinfo(
                "成功", f"免绑包已生成:\n{result}\n\n可以关闭本窗口或继续处理其他APK。"))
        except Exception as ex:
            error_msg = str(ex)
            print(f"\n❌ 处理失败: {error_msg}")
            self.root.after(0, lambda: messagebox.showerror("错误", error_msg))
        finally:
            self.root.after(0, self.reset_ui)

    def reset_ui(self):
        self.progress.stop()
        self.progress.pack_forget()
        self.start_btn.configure(state="normal")
        self.choose_btn.configure(state="normal")
        self.file_label.configure(text="📂 拖拽 APK 文件到此处\n或点击下方按钮选择文件")
        self.apk_path = None


if __name__ == "__main__":
    if DRAG_SUPPORT:
        root = TkinterDnD.Tk()
    elif USE_CTK:
        root = ctk.CTk()
    else:
        root = tk.Tk()

    app = App(root)
    root.mainloop()