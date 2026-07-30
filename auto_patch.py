import os
import sys
import shutil
import xml.etree.ElementTree as ET
import subprocess
import glob
import re

def resource_path(relative_path):
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

def setup_java():
    if getattr(sys, 'frozen', False):
        java_dir = resource_path("jre")
        java_bin = os.path.join(java_dir, "bin")
        os.environ["JAVA_HOME"] = java_dir
        os.environ["PATH"] = java_bin + os.pathsep + os.environ.get("PATH", "")
        return os.path.join(java_bin, "java.exe")
    return "java"

java_exe = setup_java()

# ---------- 配置 ----------
APKTOOL = resource_path("apktool.jar")
APKSIGNER = resource_path("apksigner.jar")
KEYSTORE = resource_path("mykey.keystore")
KEY_PASS = "123456"
KEY_ALIAS = "myalias"
UNPACK_DIR = "temp_unpack"
UNSIGNED_APK = "output_unsigned.apk"
LOCAL_APK = "game.apk"
ADB_EXE = resource_path("adb.exe")

SO_PATCH_ORIGINAL = bytes([0x4A, 0xAC, 0x8E])
SO_PATCH_NEW = bytes([0x0A, 0x00, 0x80])

UNSUPPORTED_APP_CLASSES = ["HwApplication", "HuaweiApplication"]
UNSUPPORTED_PACKAGE_KEYWORDS = ["huawei"]

def run_cmd(cmd):
    if java_exe != "java":
        cmd = cmd.replace("java ", f'"{java_exe}" ')
        cmd = cmd.replace("java\"", f'"{java_exe}"')
    print(f"> {cmd}")
    subprocess.run(cmd, shell=True, check=True)

def get_adb_devices():
    common_ports = ["16416", "7555", "5555"]
    for port in common_ports:
        subprocess.run(f'"{ADB_EXE}" connect 127.0.0.1:{port}', shell=True, capture_output=True)
    result = subprocess.run(f'"{ADB_EXE}" devices', shell=True, capture_output=True, text=True)
    devices = []
    for line in result.stdout.splitlines():
        if "device" in line and "List" not in line:
            serial = line.split()[0]
            devices.append(serial)
    return devices

def find_game_on_device(device_serial):
    cmd = f'"{ADB_EXE}" -s {device_serial} shell pm list packages'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    packages = []
    for line in result.stdout.splitlines():
        pkg = line.replace("package:", "").strip()
        if pkg.startswith("com.popcap.pvz2"):
            packages.append(pkg)
    return packages

def pull_apk_from_device(device_serial, package_name, local_name):
    cmd = f'"{ADB_EXE}" -s {device_serial} shell pm path {package_name}'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    apk_path = None
    for line in result.stdout.splitlines():
        if line.startswith("package:"):
            apk_path = line.replace("package:", "").strip()
            break
    if not apk_path:
        raise Exception(f"无法获取 {package_name} 的 APK 路径")
    print(f"📥 正在从设备拉取 {package_name} ...")
    run_cmd(f'"{ADB_EXE}" -s {device_serial} pull {apk_path} {local_name}')
    return local_name

def choose_package(packages):
    if len(packages) == 1:
        return packages[0]
    print("检测到多个植物大战僵尸2渠道包：")
    for idx, pkg in enumerate(packages, 1):
        print(f"  {idx}. {pkg}")
    while True:
        choice = input("请输入序号选择要免绑的渠道（默认1）: ").strip()
        if choice == "":
            return packages[0]
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(packages):
                return packages[idx]
        except:
            pass
        print("❌ 输入无效，请重新选择")

def get_input_apk():
    devices = get_adb_devices()
    if devices:
        device = devices[0]
        print(f"📱 已连接设备: {device}")
        packages = find_game_on_device(device)
        if packages:
            pkg = choose_package(packages)
            return pull_apk_from_device(device, pkg, LOCAL_APK)
        else:
            print("⚠️ 未在设备中找到植物大战僵尸2，切换为本地模式...")
    else:
        print("⚠️ 未检测到 adb 设备，切换为本地模式...")

    output_names = ["免绑包.apk", "免绑包_", "自动免绑包.apk", "小米免绑包.apk", "4399免绑包.apk", "华为免绑包.apk", UNSIGNED_APK, "output_unsigned-signed.apk"]
    apks = [f for f in glob.glob("*.apk") if not any(f.startswith(prefix) for prefix in output_names)]
    if len(apks) == 0:
        sys.exit("❌ 当前目录未找到待处理的 APK，且无法从设备获取。")
    elif len(apks) > 1:
        print("❌ 检测到多个 APK 文件，请只保留一个待处理的渠道包：")
        for apk in apks:
            print(f"    - {apk}")
        sys.exit(1)
    return apks[0]

def apply_patches():
    patch_dir = resource_path("patch_files")
    if not os.path.exists(patch_dir):
        return
    for root, dirs, files in os.walk(patch_dir):
        for file in files:
            if file == "AndroidManifest.xml":
                continue
            src = os.path.join(root, file)
            rel = os.path.relpath(src, patch_dir)
            dst = os.path.join(UNPACK_DIR, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)

def clean_original_meta():
    meta_path = os.path.join(UNPACK_DIR, "original", "META-INF")
    if os.path.exists(meta_path):
        shutil.rmtree(meta_path)
        print("[清理] 已删除 original/META-INF 目录，避免签名冲突")

def get_app_class():
    tree = ET.parse(os.path.join(UNPACK_DIR, "AndroidManifest.xml"))
    root = tree.getroot()
    ns = "http://schemas.android.com/apk/res/android"
    app_name = root.find("application").attrib.get(f"{{{ns}}}name", None)
    package = root.attrib.get("package", "")
    return package, app_name

def find_all_smali_paths(class_name):
    found = []
    search_pattern = os.path.join(UNPACK_DIR, "smali*", class_name.replace(".", os.sep) + ".smali")
    matches = glob.glob(search_pattern)
    found.extend(matches)
    for root, dirs, files in os.walk(UNPACK_DIR):
        for file in files:
            if file == class_name.split('.')[-1] + ".smali" and root.replace(os.sep, "/").endswith(class_name.replace(".", "/").rsplit("/", 1)[0]):
                full = os.path.join(root, file)
                if full not in found:
                    found.append(full)
    return found

def inject_init(class_name):
    paths = find_all_smali_paths(class_name)
    if not paths:
        sys.exit(f"未找到 {class_name} 的 smali 文件，注入失败。")
    for smali_path in paths:
        print(f"[*] 找到 smali: {smali_path}")
        with open(smali_path, "r", encoding="utf-8") as f:
            content = f.read()

        inject_code = "    invoke-static {p0}, Lbin/mt/signature/KillerApplication;->init(Landroid/content/Context;)V\n"

        if ".method protected onCreate()V" in content or ".method public onCreate()V" in content:
            lines = content.split("\n")
            new_lines = []
            in_oncreate = False
            inserted = False
            for i, line in enumerate(lines):
                new_lines.append(line)
                if ".method protected onCreate()V" in line or ".method public onCreate()V" in line:
                    in_oncreate = True
                    continue
                if in_oncreate and not inserted:
                    if line.strip().startswith(".prologue") or (line.strip() and not line.strip().startswith(".")):
                        new_lines.insert(len(new_lines)-1, inject_code)
                        inserted = True
                if in_oncreate and ".end method" in line:
                    in_oncreate = False
            if not inserted:
                print(f"    [!] 警告：{smali_path} 中未找到插入点，跳过")
                continue
            content = "\n".join(new_lines)
        else:
            last_method_end = content.rfind(".end method")
            if last_method_end == -1:
                print(f"    [!] 警告：{smali_path} 结构异常，跳过")
                continue
            insert_pos = content.find("\n", last_method_end) + 1
            new_method = (
                "\n.method protected onCreate()V\n"
                "    .registers 1\n\n"
                f"{inject_code}\n"
                "    return-void\n"
                ".end method\n"
            )
            content = content[:insert_pos] + new_method + content[insert_pos:]

        with open(smali_path, "w", encoding="utf-8") as f:
            f.write(content)
    print(f"[*] 注入完成: {class_name}（共处理 {len(paths)} 个文件）")

def check_unsupported(package, app_class):
    for kw in UNSUPPORTED_PACKAGE_KEYWORDS:
        if kw.lower() in package.lower():
            sys.exit(f"❌ 检测到华为渠道包（包名包含 '{kw}'），暂不支持免绑。")
    if app_class:
        for unsupported_cls in UNSUPPORTED_APP_CLASSES:
            if unsupported_cls.lower() in app_class.lower():
                sys.exit(f"❌ 检测到华为渠道 Application ({app_class})，暂不支持免绑。")

def lower_target_sdk():
    manifest_path = os.path.join(UNPACK_DIR, "AndroidManifest.xml")
    if not os.path.exists(manifest_path):
        print("[警告] 未找到 AndroidManifest.xml")
        return
    with open(manifest_path, "r", encoding="utf-8") as f:
        content = f.read()

    if '<uses-sdk ' in content:
        content = re.sub(r'targetSdkVersion="[^"]*"', 'targetSdkVersion="29"', content)
    else:
        content = content.replace(
            '<application',
            '<uses-sdk android:targetSdkVersion="29" />\n    <application'
        )

    with open(manifest_path, "w", encoding="utf-8") as f:
        f.write(content)
    print("[修改] targetSdkVersion 已强制设为 29")

def patch_libsrc():
    so_path = os.path.join(UNPACK_DIR, "lib", "arm64-v8a", "libSrc.so")
    if not os.path.exists(so_path):
        print("[警告] 未找到 libSrc.so，跳过 so 补丁")
        return
    with open(so_path, "rb") as f:
        data = bytearray(f.read())

    pos = data.find(SO_PATCH_ORIGINAL)
    if pos == -1:
        print("[警告] 未在 libSrc.so 中找到待修改字节序列，可能已不需要补丁或版本不匹配，跳过")
        return

    data[pos:pos+3] = SO_PATCH_NEW
    with open(so_path, "wb") as f:
        f.write(data)
    print(f"[补丁] 已修补 libSrc.so 偏移 {hex(pos)} 处 3 字节")

def modify_package(new_package):
    """修改 AndroidManifest.xml 中的 package 属性"""
    manifest_path = os.path.join(UNPACK_DIR, "AndroidManifest.xml")
    if not os.path.exists(manifest_path):
        print("[警告] 未找到 AndroidManifest.xml")
        return
    tree = ET.parse(manifest_path)
    root = tree.getroot()
    old_package = root.attrib.get("package", "")
    if not old_package:
        print("[警告] 原始包名为空，无法修改")
        return
    root.set("package", new_package)
    tree.write(manifest_path, encoding="utf-8", xml_declaration=True)
    print(f"[修改] 包名已从 {old_package} 改为 {new_package}")

def clean_temp_files():
    temp_items = [UNPACK_DIR, UNSIGNED_APK]
    for item in temp_items:
        if os.path.exists(item):
            try:
                if os.path.isdir(item):
                    shutil.rmtree(item)
                    print(f"[清理] 已删除目录: {item}")
                else:
                    os.remove(item)
                    print(f"[清理] 已删除文件: {item}")
            except Exception as e:
                print(f"[警告] 清理 {item} 失败: {e}")

def process_apk(apk_path, output_dir=None, custom_name=None, new_package=None):
    """处理单个 APK，返回生成的免绑包路径。
    output_dir: 输出目录，默认为当前工作目录
    custom_name: 自定义输出文件名（不含.apk），为 None 时使用默认命名
    new_package: 自定义内部包名，为 None 时不修改
    """
    global java_exe
    import tempfile
    original_dir = os.getcwd()
    tmp_dir = tempfile.mkdtemp()
    try:
        os.chdir(tmp_dir)
        input_apk = os.path.join(tmp_dir, "input.apk")
        shutil.copy2(apk_path, input_apk)

        print(f"📦 待处理文件: {input_apk}")
        if os.path.exists(UNPACK_DIR):
            shutil.rmtree(UNPACK_DIR)
        run_cmd(f'java -jar "{APKTOOL}" d -f "{input_apk}" -o "{UNPACK_DIR}"')

        # 修改包名（可选）
        if new_package:
            modify_package(new_package)

        package, app_class = get_app_class()
        if not app_class:
            app_class = "android.app.Application"
            print("[*] 未定义自定义 Application，将使用默认类。")
        print(f"包名: {package}")
        print(f"Application: {app_class}")
        check_unsupported(package, app_class)

        apply_patches()
        clean_original_meta()
        patch_libsrc()
        lower_target_sdk()
        inject_init(app_class)

        if os.path.exists(UNSIGNED_APK):
            os.remove(UNSIGNED_APK)
        run_cmd(f'java -jar "{APKTOOL}" b "{UNPACK_DIR}" -o "{UNSIGNED_APK}"')

        # 使用自定义名称或默认命名
        if custom_name:
            signed_apk = f"{custom_name}.apk"
        else:
            signed_apk = f"免绑包_{package}.apk"

        if os.path.exists(signed_apk):
            os.remove(signed_apk)
        run_cmd(
            f'java -jar "{APKSIGNER}" sign --ks "{KEYSTORE}" '
            f'--ks-pass pass:{KEY_PASS} --ks-key-alias {KEY_ALIAS} '
            f'--out "{signed_apk}" "{UNSIGNED_APK}"'
        )

        clean_temp_files()

        dest_dir = output_dir if output_dir else original_dir
        result_path = os.path.join(dest_dir, signed_apk)
        if os.path.exists(result_path):
            os.remove(result_path)
        shutil.move(os.path.join(tmp_dir, signed_apk), result_path)
        print(f"📱 最终安装包: {result_path}")
        return result_path
    finally:
        os.chdir(original_dir)
        shutil.rmtree(tmp_dir, ignore_errors=True)

def main():
    input_apk = get_input_apk()
    process_apk(input_apk)

if __name__ == "__main__":
    main()