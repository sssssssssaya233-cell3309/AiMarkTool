# AiMarkTool Windows 便携版

适用于 64 位 Windows 10 22H2 / Windows 11。无需安装 Python，也无需单独安装
FFmpeg。

## 使用方法

1. 下载并完整解压 `Windows版.zip`。
2. 双击 `AiMarkTool.exe`。
3. 添加视频、设置水印，然后选择输出目录并开始处理。

请不要只把 `AiMarkTool.exe` 单独移走；`ffmpeg.exe` 和 `ffprobe.exe` 必须与它放在
同一文件夹中。

默认输出位置为当前用户的 `Videos\Watermarked`。同名文件会自动编号，不会覆盖
原文件。

## 下载自动构建版本

打开仓库的 **Actions** 页面，选择 **Build Windows portable**，进入最近一次成功
的运行，在 **Artifacts** 区域下载 `Windows版`。下载所得 artifact 解压后会得到
`Windows版.zip`，再次解压即可使用。

也可以在该工作流页面点击 **Run workflow** 手动生成最新版。

## Windows 安全提示

当前构建未进行商业代码签名。Windows SmartScreen 可能显示“无法识别的应用”。
请仅从本仓库的 GitHub Actions 下载，并在运行前使用 Windows Defender 扫描。

## 文件说明

- `AiMarkTool.exe`：水印工具主程序。
- `ffmpeg.exe`：视频处理引擎。
- `ffprobe.exe`：视频信息读取工具。
- `THIRD-PARTY-NOTICES.txt`：FFmpeg 来源与许可说明。

## 开发者本地构建

在仓库根目录使用 Windows PowerShell：

```powershell
py -3.12 -m venv .venv-windows
.\.venv-windows\Scripts\python.exe -m pip install -r .\Windows版\requirements-build.txt
.\.venv-windows\Scripts\pyinstaller.exe --noconfirm --clean .\Windows版\AiMarkTool.spec
```

PyInstaller 不能在 macOS 上交叉生成 Windows `.exe`，请在 Windows 环境构建。
