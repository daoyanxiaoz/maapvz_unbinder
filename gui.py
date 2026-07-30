import sys
import os
import threading
import subprocess
import tkinter as tk
from tkinter import messagebox, filedialog

os.environ["CTK_DPI_AWARE"] = "0"

try:
    import customtkinter as ctk
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")
    USE_CTK = True
except ImportError:
    import tkinter as tk
    USE_CTK = False

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DRAG_SUPPORT = True
except ImportError:
    DRAG_SUPPORT = False

from auto_patch import process_apk, setup_java, resource_path

java_exe = setup_java()

ADB_EXE = resource_path("adb.exe")
ADB_AVAILABLE = os.path.exists(ADB_EXE) if ADB_EXE else False

class RedirectText:
    def __init__(self, text_widget):
        self.text_widget = text_widget
    def write(self, string):
        self.text_widget.insert(tk.END, string)
        self.text_widget.see(tk.END)
        self.text_widget.update_idletasks()
    def flush(self):
        pass

class BatchWindow(ctk.CTkToplevel if USE_CTK else tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("连接模拟器")
        self.geometry("750x650")
        self.minsize(600, 480)
        self.parent = parent
        self.device_serial = None
        self.packages = []          # 模拟器包名列表
        self.local_files = []       # 本地APK路径列表

        self.block_update_dimensions_event = lambda: None
        self.unblock_update_dimensions_event = lambda: None

        self.transient(parent)
        parent.attributes('-alpha', 1.0)

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.create_widgets()
        self.after(500, self.refresh_devices)

    def on_close(self):
        self.destroy()
        self.parent.focus_force()
        self.parent.attributes('-alpha', 1.0)

    def create_widgets(self):
        main_frame = ctk.CTkFrame(self) if USE_CTK else tk.Frame(self)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        label_cls = ctk.CTkLabel if USE_CTK else tk.Label
        btn_cls = ctk.CTkButton if USE_CTK else tk.Button
        combo_cls = ctk.CTkComboBox if USE_CTK else tk.ttk.Combobox

        # 标题
        label_cls(main_frame, text="📱 连接模拟器", font=("Microsoft YaHei", 14, "bold")).pack(anchor="w", pady=5)

        # 自动扫描区域
        auto_frame = ctk.CTkFrame(main_frame) if USE_CTK else tk.Frame(main_frame)
        auto_frame.pack(fill="x", pady=5)
        label_cls(auto_frame, text="自动扫描设备：", font=("Microsoft YaHei", 10)).pack(side="left")
        self.refresh_btn = btn_cls(auto_frame, text="刷新", command=self.refresh_devices, width=80)
        self.refresh_btn.pack(side="left", padx=10)
        self.device_combo = combo_cls(auto_frame, values=[], width=200)
        self.device_combo.pack(side="left", padx=5)
        self.connect_btn = btn_cls(auto_frame, text="连接此设备", command=self.connect_device, width=100)
        self.connect_btn.pack(side="left", padx=5)

        # 手动连接区域
        manual_frame = ctk.CTkFrame(main_frame) if USE_CTK else tk.Frame(main_frame)
        manual_frame.pack(fill="x", pady=5)
        label_cls(manual_frame, text="手动端口连接：", font=("Microsoft YaHei", 10)).pack(side="left")
        self.port_entry = ctk.CTkEntry(manual_frame, width=80, placeholder_text="7555") if USE_CTK else tk.Entry(manual_frame, width=10)
        self.port_entry.pack(side="left", padx=5)
        self.manual_btn = btn_cls(manual_frame, text="手动连接", command=self.manual_connect, width=100)
        self.manual_btn.pack(side="left", padx=5)

        # 本地APK添加区域
        local_frame = ctk.CTkFrame(main_frame) if USE_CTK else tk.Frame(main_frame)
        local_frame.pack(fill="x", pady=5)
        label_cls(local_frame, text="本地文件：", font=("Microsoft YaHei", 10)).pack(side="left")
        self.add_local_btn = btn_cls(local_frame, text="选择APK文件", command=self.add_local_apks, width=110)
        self.add_local_btn.pack(side="left", padx=5)

        # 包列表
        pkg_frame = ctk.CTkFrame(main_frame) if USE_CTK else tk.Frame(main_frame)
        pkg_frame.pack(fill="both", expand=True, pady=10)
        label_cls(pkg_frame, text="📦 待处理列表（可多选）", font=("Microsoft YaHei", 12)).pack(anchor="w", padx=5)
        self.pkg_listbox = tk.Listbox(pkg_frame, selectmode="multiple", font=("Microsoft YaHei", 10),
                                      bg="#2b2b2b", fg="#dcdcdc", selectbackground="#4a9eff", height=8)
        self.pkg_listbox.pack(fill="both", expand=True, padx=5, pady=5)

        # 自定义选项区域
        option_frame = ctk.CTkFrame(main_frame) if USE_CTK else tk.Frame(main_frame)
        option_frame.pack(fill="x", pady=5)

        # 新包名（内部包名）
        label_cls(option_frame, text="新包名（可选）：", font=("Microsoft YaHei", 10)).pack(side="left")
        self.new_package_entry = ctk.CTkEntry(option_frame, width=200, placeholder_text="如 com.example.pvz2") if USE_CTK else tk.Entry(option_frame, width=25)
        self.new_package_entry.pack(side="left", padx=5)
        label_cls(option_frame, text="※仅对单个选中项有效", font=("Microsoft YaHei", 8)).pack(side="left")

        # 输出文件名
        name_frame = ctk.CTkFrame(main_frame) if USE_CTK else tk.Frame(main_frame)
        name_frame.pack(fill="x", pady=5)
        label_cls(name_frame, text="输出文件名（可选）：", font=("Microsoft YaHei", 10)).pack(side="left")
        self.custom_name_entry = ctk.CTkEntry(name_frame, width=160, placeholder_text="自定义名称（不含.apk）") if USE_CTK else tk.Entry(name_frame, width=20)
        self.custom_name_entry.pack(side="left", padx=5)

        # 按钮行
        btn_frame = ctk.CTkFrame(main_frame) if USE_CTK else tk.Frame(main_frame)
        btn_frame.pack(fill="x", pady=10)
        self.select_all_btn = btn_cls(btn_frame, text="全选", command=self.select_all, width=80)
        self.select_all_btn.pack(side="left", padx=5)
        self.process_btn = btn_cls(btn_frame, text="处理选中的安装包", command=self.process_selected,
                                   fg_color="#2b7a4b", hover_color="#1e5a37", width=140) if USE_CTK else tk.Button(
            btn_frame, text="处理选中的安装包", command=self.process_selected, bg="#2b7a4b", fg="white", width=15)
        self.process_btn.pack(side="left", padx=5)

        # 进度条
        self.progress = ctk.CTkProgressBar(main_frame, mode="indeterminate", height=8) if USE_CTK else tk.ttk.Progressbar(main_frame, mode="indeterminate")
        self.progress.pack(fill="x", padx=10, pady=5)
        self.progress.pack_forget()

        # 日志
        self.log_text = ctk.CTkTextbox(main_frame, font=("Consolas", 10), fg_color="#1e1e1e",
                                       text_color="#dcdcdc", wrap="word", height=8) if USE_CTK else tk.Text(
            main_frame, font=("Consolas", 10), bg="#1e1e1e", fg="#dcdcdc", wrap="word", height=8)
        self.log_text.pack(fill="both", expand=True, padx=5, pady=5)

        if not ADB_AVAILABLE:
            self.log("错误：找不到 adb 程序，请将 adb.exe 及 DLL 放在程序目录。")
            self.refresh_btn.configure(state="disabled")
            self.manual_btn.configure(state="disabled")
            self.connect_btn.configure(state="disabled")

    def log(self, msg):
        if self.winfo_exists():
            self.log_text.insert(tk.END, msg + "\n")
            self.log_text.see(tk.END)

    def _run_adb(self, args):
        if not ADB_AVAILABLE:
            return "找不到 adb", "ADB 不可用"
        try:
            proc = subprocess.run(
                f'"{ADB_EXE}" {args}',
                shell=True,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=10
            )
            return proc.stdout, proc.stderr
        except Exception as e:
            return "", str(e)

    def refresh_devices(self):
        if not ADB_AVAILABLE or not self.winfo_exists():
            self._update_device_list([])
            return
        def task():
            if not self.winfo_exists(): return
            self.refresh_btn.configure(state="disabled")
            self.log("正在扫描设备...")
            stdout, _ = self._run_adb("devices")
            devices = []
            for line in stdout.splitlines():
                if "device" in line and "List" not in line:
                    devices.append(line.split()[0])
            for port in ["16416", "7555", "5555"]:
                self._run_adb(f"connect 127.0.0.1:{port}")
            stdout2, _ = self._run_adb("devices")
            for line in stdout2.splitlines():
                if "device" in line and "List" not in line:
                    s = line.split()[0]
                    if s not in devices:
                        devices.append(s)
            self.after(0, lambda: self._update_device_list(devices))
        threading.Thread(target=task, daemon=True).start()

    def _update_device_list(self, devices):
        if not self.winfo_exists(): return
        self.refresh_btn.configure(state="normal" if ADB_AVAILABLE else "disabled")
        if devices:
            if USE_CTK:
                self.device_combo.configure(values=devices)
            else:
                self.device_combo['values'] = devices
            self.device_combo.set(devices[0])
            self.log(f"发现 {len(devices)} 个设备")
        else:
            self.log("未发现设备。请确认模拟器已开启ADB调试，或使用下方手动端口连接。")

    def manual_connect(self):
        if not ADB_AVAILABLE:
            messagebox.showerror("错误", "ADB 不可用，请检查程序目录中的 adb.exe")
            return
        port = self.port_entry.get().strip()
        if not port:
            messagebox.showerror("错误", "请输入端口号（如7555）")
            return
        self.log(f"正在连接 127.0.0.1:{port} ...")
        stdout, stderr = self._run_adb(f"connect 127.0.0.1:{port}")
        if "connected" in stdout.lower() or "already connected" in stdout.lower():
            self.log(f"成功连接到 {port}")
            self.refresh_devices()
        else:
            self.log(f"连接失败: {stdout} {stderr}")
            messagebox.showerror("连接失败", f"无法连接到 127.0.0.1:{port}\n{stderr}")

    def connect_device(self):
        if not self.winfo_exists(): return
        serial = self.device_combo.get()
        if not serial:
            messagebox.showerror("错误", "请先选择一个设备")
            return
        self.device_serial = serial
        self.log(f"已连接设备: {serial}")
        self.packages = []
        self.local_files = []
        self.pkg_listbox.delete(0, tk.END)
        def task():
            if not self.winfo_exists(): return
            try:
                cmd = f' -s {serial} shell pm list packages'
                stdout, _ = self._run_adb(cmd)
                pkgs = [line.replace("package:", "").strip() for line in stdout.splitlines()
                        if line.startswith("package:") and "com.popcap.pvz2" in line]
                self.after(0, lambda: self._update_package_list(pkgs, clear_local=True))
            except Exception as e:
                self.after(0, lambda: self.log(f"获取包列表失败: {e}"))
        threading.Thread(target=task, daemon=True).start()

    def add_local_apks(self):
        files = filedialog.askopenfilenames(title="选择 APK 文件", filetypes=[("APK files", "*.apk")])
        if files:
            for f in files:
                self.local_files.append(f)
                self.pkg_listbox.insert(tk.END, f"local:{os.path.basename(f)}")
            self.log(f"已添加 {len(files)} 个本地 APK 文件")

    def _update_package_list(self, pkgs, clear_local=False):
        if not self.winfo_exists(): return
        if clear_local:
            self.local_files = []
            self.pkg_listbox.delete(0, tk.END)
        if pkgs:
            self.packages = pkgs
            for pkg in pkgs:
                self.pkg_listbox.insert(tk.END, pkg)
            self.log(f"找到 {len(pkgs)} 个游戏包")
        else:
            self.log("未找到植物大战僵尸2安装包")

    def select_all(self):
        if self.winfo_exists():
            self.pkg_listbox.select_set(0, tk.END)

    def process_selected(self):
        if not self.winfo_exists(): return
        selected_indices = self.pkg_listbox.curselection()
        if not selected_indices:
            messagebox.showerror("错误", "请至少选择一个安装包")
            return

        # 解析选中项
        all_items = []
        for i in range(self.pkg_listbox.size()):
            text = self.pkg_listbox.get(i)
            if text.startswith("local:"):
                basename = text[6:]
                matched = [f for f in self.local_files if os.path.basename(f) == basename]
                if matched:
                    all_items.append(('local', matched[0]))
            else:
                all_items.append(('device', text))

        selected = [all_items[i] for i in selected_indices if i < len(all_items)]

        # 新包名仅对单个选中项有效
        new_package = None
        if len(selected) == 1:
            new_package = self.new_package_entry.get().strip() or None
        elif self.new_package_entry.get().strip():
            messagebox.showwarning("提示", "修改内部包名仅对单个安装包有效，本次将忽略包名修改。")

        # 自定义文件名仅对单个选中项有效
        custom_name = None
        if len(selected) == 1:
            custom_name = self.custom_name_entry.get().strip() or None
        elif self.custom_name_entry.get().strip():
            messagebox.showwarning("提示", "自定义文件名仅对单个安装包有效，本次将忽略。")

        self.process_btn.configure(state="disabled")
        self.progress.pack(fill="x", padx=10, pady=5)
        self.progress.start()
        threading.Thread(target=self._run_batch, args=(selected, custom_name, new_package), daemon=True).start()

    def _run_batch(self, items, custom_name, new_package):
        for typ, val in items:
            if not self.winfo_exists(): return
            try:
                if typ == 'device':
                    self.log(f"正在处理 {val} (模拟器)...")
                    local_tmp = os.path.join(os.getcwd(), f"temp_{val}.apk")
                    path_cmd = f' -s {self.device_serial} shell pm path {val}'
                    stdout, _ = self._run_adb(path_cmd)
                    apk_path = None
                    for line in stdout.splitlines():
                        if line.startswith("package:"):
                            apk_path = line.replace("package:", "").strip()
                            break
                    if not apk_path:
                        self.log(f"❌ 无法获取 {val} 的路径")
                        continue
                    self._run_adb(f' -s {self.device_serial} pull {apk_path} {local_tmp}')
                    result = process_apk(local_tmp, output_dir=os.getcwd(),
                                         custom_name=custom_name if len(items)==1 else None,
                                         new_package=new_package if len(items)==1 else None)
                    self.log(f"✅ {val} 完成: {result}")
                    try: os.remove(local_tmp)
                    except: pass
                else:  # local
                    self.log(f"正在处理 {os.path.basename(val)} (本地)...")
                    result = process_apk(val, output_dir=os.getcwd(),
                                         custom_name=custom_name if len(items)==1 else None,
                                         new_package=new_package if len(items)==1 else None)
                    self.log(f"✅ {os.path.basename(val)} 完成: {result}")
            except Exception as e:
                self.log(f"❌ 失败: {e}")
        if self.winfo_exists():
            self.progress.stop()
            self.progress.pack_forget()
            self.process_btn.configure(state="normal")
            self.log("批量处理完成")

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("maapvz 免绑小助手")
        self.root.geometry("750x600")
        self.root.minsize(650, 520)

        self.root.block_update_dimensions_event = lambda: None
        self.root.unblock_update_dimensions_event = lambda: None
        self.root.attributes('-alpha', 1.0)

        try:
            icon_path = resource_path("icon.ico")
            if os.path.exists(icon_path):
                self.root.iconbitmap(icon_path)
        except:
            pass

        self.apk_path = None
        self.use_ctk = USE_CTK
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
        main = ctk.CTkFrame(self.root, corner_radius=15, fg_color="#1a1a1a") if self.use_ctk else tk.Frame(self.root, bg="#1a1a1a")
        main.pack(fill="both", expand=True, padx=10, pady=10)

        title_font = ctk.CTkFont(family="Microsoft YaHei", size=20, weight="bold") if self.use_ctk else ("Microsoft YaHei", 20, "bold")
        self.title_label = ctk.CTkLabel(main, text="🌻 植物大战僵尸2 免绑小助手", font=title_font, text_color="#4a9eff") if self.use_ctk else tk.Label(main, text="🌻 植物大战僵尸2 免绑小助手", font=title_font, fg="#4a9eff", bg="#1a1a1a")
        self.title_label.pack(pady=(15, 10))

        self.drop_frame = ctk.CTkFrame(main, corner_radius=10, border_width=2, fg_color="transparent", border_color="#3b3b3b") if self.use_ctk else tk.Frame(main, bg="#2b2b2b", relief="groove", bd=2)
        self.drop_frame.pack(fill="x", padx=20, pady=10, ipady=35)

        self.file_label = ctk.CTkLabel(self.drop_frame, text="📂 拖拽 APK 文件到此处\n或点击下方按钮选择文件",
                                       font=ctk.CTkFont(family="Microsoft YaHei", size=12) if self.use_ctk else ("Microsoft YaHei", 12),
                                       justify="center", text_color="#aaaaaa") if self.use_ctk else tk.Label(
            self.drop_frame, text="📂 拖拽 APK 文件到此处\n或点击下方按钮选择文件", font=("Microsoft YaHei", 12), fg="#aaaaaa", bg="#2b2b2b")
        self.file_label.pack(expand=True)

        if DRAG_SUPPORT:
            if self.use_ctk:
                self.drop_frame.drop_target_register(DND_FILES)
                self.drop_frame.dnd_bind('<<Drop>>', self.on_drop)
            else:
                self.root.drop_target_register(DND_FILES)
                self.root.dnd_bind('<<Drop>>', self.on_drop)

        btn_frame = ctk.CTkFrame(main, fg_color="transparent") if self.use_ctk else tk.Frame(main, bg="#1a1a1a")
        btn_frame.pack(pady=15)

        self.choose_btn = ctk.CTkButton(btn_frame, text="📁 选择 APK", command=self.choose_file, width=140, height=40, corner_radius=8,
                                        fg_color="#2b5b84", hover_color="#1e405e", font=ctk.CTkFont(size=14, weight="bold")) if self.use_ctk else tk.Button(btn_frame, text="📁 选择 APK", command=self.choose_file, width=15)
        self.choose_btn.pack(side="left", padx=10)

        self.start_btn = ctk.CTkButton(btn_frame, text="🚀 开始免绑", command=self.start_process, state="disabled", width=140, height=40,
                                       corner_radius=8, fg_color="#2b7a4b", hover_color="#1e5a37", font=ctk.CTkFont(size=14, weight="bold")) if self.use_ctk else tk.Button(btn_frame, text="🚀 开始免绑", command=self.start_process, state="disabled", width=15)
        self.start_btn.pack(side="left", padx=10)

        self.batch_btn = ctk.CTkButton(btn_frame, text="📥 连接模拟器", command=self.open_batch, width=140, height=40,
                                       corner_radius=8, fg_color="#555", hover_color="#333", font=ctk.CTkFont(size=14, weight="bold")) if self.use_ctk else tk.Button(btn_frame, text="📥 连接模拟器", command=self.open_batch, width=15)
        self.batch_btn.pack(side="left", padx=10)

        # 选项区域
        option_frame = ctk.CTkFrame(main, fg_color="transparent") if self.use_ctk else tk.Frame(main, bg="#1a1a1a")
        option_frame.pack(fill="x", padx=20, pady=(10, 0))

        label_cls = ctk.CTkLabel if USE_CTK else tk.Label

        # 新包名
        label_cls(option_frame, text="新包名（可选）：", font=("Microsoft YaHei", 10)).pack(side="left")
        self.new_package_entry = ctk.CTkEntry(option_frame, width=180, placeholder_text="修改内部包名") if USE_CTK else tk.Entry(option_frame, width=22)
        self.new_package_entry.pack(side="left", padx=5)

        # 输出文件名
        label_cls(option_frame, text="输出文件名（可选）：", font=("Microsoft YaHei", 10)).pack(side="left", padx=(15, 0))
        self.custom_name_entry = ctk.CTkEntry(option_frame, width=150, placeholder_text="不含.apk") if USE_CTK else tk.Entry(option_frame, width=18)
        self.custom_name_entry.pack(side="left", padx=5)

        self.progress = ctk.CTkProgressBar(main, height=8, corner_radius=4, progress_color="#4a9eff") if self.use_ctk else tk.ttk.Progressbar(main, mode="indeterminate")
        self.progress.pack_forget()

        log_frame = ctk.CTkFrame(main, corner_radius=10, fg_color="#1e1e1e") if self.use_ctk else tk.Frame(main, bg="#1e1e1e")
        log_frame.pack(fill="both", expand=True, padx=20, pady=(15, 10))
        self.log_text = ctk.CTkTextbox(log_frame, font=("Consolas", 11), fg_color="#1e1e1e", text_color="#dcdcdc", corner_radius=8, wrap="word") if self.use_ctk else tk.Text(log_frame, font=("Consolas", 11), bg="#1e1e1e", fg="#dcdcdc", insertbackground="white", relief="flat", borderwidth=0, padx=15, pady=15)
        self.log_text.pack(fill="both", expand=True, padx=5, pady=5)

        status_text = f"v2.0 | Java: {'内嵌' if java_exe != 'java' else '系统'} | ADB: {'可用' if ADB_AVAILABLE else '缺失'}"
        self.status_label = ctk.CTkLabel(main, text=status_text, font=("Microsoft YaHei", 10), text_color="#888888") if self.use_ctk else tk.Label(main, text=status_text, font=("Microsoft YaHei", 10), fg="#888888", bg="#1a1a1a")
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
        path = filedialog.askopenfilename(title="选择 APK 文件", filetypes=[("APK files", "*.apk")])
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

        new_package = self.new_package_entry.get().strip() or None
        custom_name = self.custom_name_entry.get().strip() or None
        print(f"开始处理: {self.apk_path}\n")
        threading.Thread(target=self.run_process, args=(custom_name, new_package), daemon=True).start()

    def run_process(self, custom_name, new_package):
        try:
            result = process_apk(self.apk_path, custom_name=custom_name, new_package=new_package)
            print(f"\n✅ 免绑成功！\n输出文件: {result}")
            self.root.after(0, lambda: messagebox.showinfo("成功", f"免绑包已生成:\n{result}"))
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

    def open_batch(self):
        if not ADB_AVAILABLE:
            messagebox.showerror("错误", "ADB 程序缺失，无法连接模拟器。请将 adb.exe 及 DLL 放在程序目录。")
            return
        self.root.attributes('-alpha', 1.0)
        BatchWindow(self.root)

if __name__ == "__main__":
    if DRAG_SUPPORT:
        root = TkinterDnD.Tk()
    elif USE_CTK:
        root = ctk.CTk()
    else:
        root = tk.Tk()
    app = App(root)
    root.mainloop()