# Kindle SYSWATCH：从越狱到极客风电脑监控屏

> 本文记录一次已经实际跑通的改造：把 Kindle Paperwhite 3（第七代，PW3）变成一块通过 Wi-Fi 自动更新的电脑状态屏，显示 CPU、GPU、内存、磁盘、网络和 Codex 每周用量。
>
> 实测设备为 **PW3 / 固件 5.16.2.1.1 / soft-float**，电脑端为 Windows 10/11、AMD Ryzen 7 5800X 和 NVIDIA RTX 4070 Ti Super。其他型号、固件或硬件可以参考架构，但越狱方法、二进制架构和传感器兼容性必须重新确认。

## 0. 先看结论

最终系统不是把 Kindle 当成普通的 HDMI/USB 显示器，而是采用下面的结构：

```text
Windows 电脑
  ├─ psutil：负载、内存、磁盘、网络
  ├─ LibreHardwareMonitor：CPU/GPU 温度、功耗、频率等
  ├─ AMD Ryzen Master SDK：Ryzen 温度后备通道
  ├─ Codex CLI：读取当前账户的每周额度
  ├─ Pillow：生成 1072 × 1448 黑白仪表盘 PNG
  └─ HTTP :8765：提供 dashboard.png
                    │
                    │ Wi-Fi / Windows 移动热点
                    ▼
Kindle
  ├─ KUAL 启动 SYSWATCH 扩展
  ├─ wget/curl 每 10 秒下载 PNG
  └─ FBInk 全屏绘制到电子墨水屏
```

这种方案的优点是 Kindle 端很轻，只负责下载和显示；复杂的硬件采集、字体、图表和布局全部由电脑完成。代价是它不是高帧率副屏，10 秒级刷新更符合电子墨水屏的特性。

项目中的主要目录如下：

```text
kindle-syswatch/
├─ kindle-extension/kindle-monitor/  # Kindle KUAL 扩展
├─ kindle_monitor/                   # Windows 监控服务和仪表盘渲染器
├─ sensor_bridge/                    # LibreHardwareMonitor 桥接程序源码
├─ config.example.toml
├─ setup.ps1
└─ Kindle_SYSWATCH_从越狱到监控屏完整教程.md
```

## 1. 风险、适用范围与准备工作

### 1.1 不要直接照抄越狱方法到其他 Kindle

Kindle 越狱高度依赖“准确型号 + 准确固件”。开始前先在：

```text
主页 → 设置 → 设备选项 → 设备信息
```

确认型号、固件版本和剩余空间，再使用 [KindleModding Jailbreak Wizard](https://kindlemodding.org/jailbreaking/) 判断当前可用方法。官方 FAQ 也明确提醒：未越狱设备通常不能随意降级；如果固件已经升级到没有漏洞的版本，只能等待新方法。[Kindle Jailbreak FAQ](https://kindlemodding.org/jailbreaking/jailbreak-faq.html)

本文的越狱章节只针对本次实测环境：

```text
Kindle Paperwhite 3（第七代 / PW3）
Firmware 5.16.2.1.1
soft-float
WinterBreak2 1.7.0
```

WinterBreak2 仓库说明其适用于 **低于 5.16.4** 的固件；不要把这一结论扩展到更新固件。[WinterBreak2](https://github.com/KindleModding/Winterbreak2)

### 1.2 开始前备份

至少复制 Kindle USB 磁盘中的这些内容：

```text
documents/
fonts/
```

如果有标注、阅读进度或侧载书籍，也一起备份相应的 `.sdr` 目录。项目中的 `backup/` 是本次操作前的书籍备份。

此外要记录：

- Kindle 型号和固件版本；
- 当前可用空间；
- Wi-Fi 能否正常连接；
- Windows 能否识别 Kindle USB 磁盘；
- Kindle 盘符。本文用 `G:\` 举例，但另一台电脑可能分配其他盘符。

### 1.3 三条重要纪律

1. 每次复制完文件都要在 Windows 中“安全弹出”，再拔数据线。
2. 安装越狱、Hotfix 或升级包时，先开启飞行模式并清理不相关的 `.bin`、`update.bin.tmp.partial`。
3. 不要混用不同教程、不同发布版本的文件。尤其不要随便从网盘或转载站下载 Hotfix、KUAL、MRPI、FBInk。

## 2. 越狱：本次 PW3 使用 WinterBreak2

### 2.1 为什么用 WinterBreak2

本次设备能打开“体验版/实验性浏览器”，但标准 Mesquito 路线不稳定，因此选择了 Mesquito-less 的 WinterBreak2。其官方步骤是：把 `wb2.zip` 解压到 Kindle 根目录，打开实验性浏览器访问触发页，然后点击 Jailbreak。[WinterBreak2 官方仓库](https://github.com/KindleModding/Winterbreak2)

注意：KindleModding 当前主教程主要描述新版 WinterBreak/Mesquito，且会随时间更新；本文保留的是 **2026 年 8 月在 PW3 5.16.2.1.1 上实际使用的 WinterBreak2 路线**。操作新设备前应重新查看[当前 WinterBreak 文档](https://kindlemodding.org/jailbreaking/WinterBreak/)。

### 2.2 复制 WinterBreak2 文件

1. 开启 Kindle 飞行模式并重启。
2. 用 USB 连接电脑，确认 Kindle 磁盘出现。
3. 在电脑上先解压 `wb2.zip`，不要直接把压缩包拖进 Kindle 后在设备中解压。
4. 把解压出的内容复制到 Kindle 根目录。

以 `G:\` 为例，最终应能看到类似：

```text
G:\winterbreak2\dialoger.html
G:\jb.sh
G:\patchedUks.sqsh
```

根目录不是 `documents`，而是打开 Kindle 盘符后第一眼看到的那一层。Kindle 内部对应 `/mnt/us/`。

5. 安全弹出 Kindle，拔掉 USB。
6. 关闭飞行模式，连接 Wi-Fi。

### 2.3 优先尝试官方触发页

在 Kindle 实验性浏览器打开：

```text
https://winterbreak2.now.sh/
```

正常应出现 Jailbreak 按钮。点击后会弹出确认框，确认执行。随后屏幕会显示终端风格文本，脚本安装开发者密钥、启用相关标志，并提示安装 Hotfix。

本次成功画面包含：

```text
Developer keys installed successfully
Enabled developer flag
Enabled mntus exec flag
Finished installing jailbreak
Please Install HOTFIX now
```

只要还没出现“Finished installing jailbreak”或“ready to install the hotfix”一类明确完成提示，就不要自作主张进入下一步。官方 FAQ 也把最终提示作为重要判断依据。[Kindle Jailbreak FAQ](https://kindlemodding.org/jailbreaking/jailbreak-faq.html)

### 2.4 避坑：网页只显示 308 Redirecting

本次访问 `winterbreak2.now.sh` 时，旧 Kindle 浏览器只显示：

```text
Redirecting (308)
The document has moved here
```

原因不是 `wb2.zip` 放错，而是托管平台把旧域名重定向到新的 Vercel 地址，老浏览器不能正确跟随现代重定向/TLS/页面脚本。直接输入新的 Vercel 地址后又出现白屏，也仍然是浏览器兼容问题，不代表越狱包失效。

遇到这种情况时，应优先查看 WinterBreak2 官方说明和当前发布页。为避免传播过时触发代码，本仓库不附带越狱包、触发页或镜像。只使用官方发布并校验过的文件，不要从网盘或未知教程下载重新打包的越狱文件。

### 2.5 越狱后的初步验证

官方 FAQ 建议在 Kindle 搜索栏输入：

```text
;log
```

出现提示框通常表示越狱有效。本次设备上 `;log` 没有给出有用结果，因此没有把它作为唯一判据；最终结合 WinterBreak2 的成功输出、Hotfix 可运行、KUAL 能启动扩展进行验证。换言之，`;log` 是辅助检查，不应盖过完整安装链的事实。

## 3. 立即安装 Hotfix

### 3.1 为什么本次不能跳过

当前 KindleModding 文档指出，某些新版 WinterBreak 包已经包含 Hotfix，可以跳过单独安装；但本次使用的 WinterBreak2 1.7.0 在屏幕上明确显示：

```text
Please Install HOTFIX now
```

因此本次必须按该发布版本的输出安装 Universal Hotfix。经验法则是：**服从你实际使用的越狱包和它的完成提示，不要用另一版本教程的一句话覆盖当前流程。**

Hotfix 的作用是安装/修复开发者密钥和持久化机制，让越狱在后续系统更新后仍有恢复入口。官方步骤可参考 [Setting Up A Hotfix](https://kindlemodding.org/jailbreaking/post-jailbreak/setting-up-a-hotfix/)。

### 3.2 安装顺序

1. 从 [KindleModding/Hotfix](https://github.com/KindleModding/Hotfix) 官方发布页下载 `Update_hotfix_universal.bin`。
2. 开启飞行模式。
3. USB 连接 Kindle，把文件复制到 USB 根目录。
4. 确认根目录没有其他不相关 `.bin` 或 `update.bin.tmp.partial`。
5. 安全弹出并拔线。
6. 进入设置菜单，选择“更新您的 Kindle”。
7. 等待更新和重启完成。
8. 回到图书馆，打开新出现的 `Run Hotfix`，让它完成最后阶段。

本次使用的是 Universal Hotfix 2.5.0；当时下载文件的 SHA-256 记录为：

```text
94D5C05254B70C4905392515411F620168AC238DB62C7DCBC48A1E31D5DE6C59
```

该哈希只用于核对本次归档版本。未来官方重新发布时，应以新发布页提供的信息为准，不要为了匹配旧哈希而下载来历不明的文件。

### 3.3 避坑：Collecting Debug Info / KPPMainAppV2

本次运行 Hotfix 后曾出现：

```text
Collecting Debug Info
Generating Core Dump file for process KPPMainAppV2
```

随后图书馆里多出一本名字很长的 `KPPMainAppV2_...` 文档。这是 Kindle 对某个进程异常生成的 core dump 包，不等于“机器变砖”或“Hotfix 一定失败”。官方 FAQ 明确说明这类文档可以安全删除；若不希望以后继续生成，可在 Kindle USB 根目录创建空文件：

```text
DISABLE_CORE_DUMP
```

PowerShell 示例，盘符按实际修改：

```powershell
New-Item -ItemType File -Path 'G:\DISABLE_CORE_DUMP' -Force
```

参考：[Kindle Jailbreak FAQ — KPPMainAppV2](https://kindlemodding.org/jailbreaking/jailbreak-faq.html)

## 4. 安装 KUAL 与 MRPI

KUAL 是 Kindle 上的扩展启动器，MRPI 是安装 Kindle 包的工具。本项目通过 KUAL 启动 SYSWATCH。

### 4.1 选择正确版本

PW3 属于 K5 及更新设备，使用现代 KUAL 的 PEKI 版本。官方当前指南要求：

- 解压 MRPI，把 `extensions` 和 `mrpackages` 复制到 Kindle 根目录；
- 解压 PEKI，把 `KUAL.sh` 与 `KUAL.jar` 放进 `documents`；
- 预留至少约 220 MB 空间；
- 删除浏览器自动添加的 `(1)`、括号或其他特殊后缀。

参考：[Installing KUAL and MRPI](https://kindlemodding.org/jailbreaking/post-jailbreak/installing-kual-mrpi/)

以 `G:\` 为例，目标结构应类似：

```text
G:\extensions\
G:\mrpackages\
G:\documents\KUAL.sh
G:\documents\KUAL.jar
```

复制后安全弹出、拔线并重启 Kindle。图书馆中应出现 `KUAL` 封面。

### 4.2 避坑：No arg passed. Select from mrpi or runme

本次安装过程中屏幕顶端出现过：

```text
No arg passed. Select from mrpi or runme
```

这不是越狱被清除，而是某个调度脚本被启动时没有收到 `mrpi` 或 `runme` 参数。常见原因包括：

- 把脚本放到了错误目录；
- 直接点了底层脚本，而不是通过正确入口运行；
- MRPI/KUAL 文件结构不完整；
- 文件名被浏览器改成了 `xxx (1)`。

解决方向不是反复点同一个文件，而是重新核对上面的目录结构、文件名和现代/旧版架构，重启后从 KUAL 或 MRPI 的标准入口运行。本次修正目录并重启后，KUAL 正常出现。

## 5. 阻止自动更新，但不要阻断 Hotfix

越狱完成后，应防止 Kindle 在联网时自动升级到不兼容固件。对于 5.11 及以上固件，常用做法是在 KUAL 中安装并运行 `Rename OTA Binaries`：

```text
KUAL → Rename OTA Binaries → Rename
```

但顺序非常重要：

```text
越狱 → Hotfix → KUAL/MRPI → 再阻止 OTA
```

不要在 Hotfix 之前先 Rename，否则系统更新入口可能忽略 `Update_hotfix_universal.bin`。以后如果要安装 Hotfix、官方更新、降级或恢复出厂，必须先：

```text
KUAL → Rename OTA Binaries → Restore
```

完成操作后再切回 `Rename`。官方也提醒，带着 OTA blocker 恢复出厂可能造成更新文件无法安装。[Disabling OTA Updates](https://kindlemodding.org/jailbreaking/post-jailbreak/disable-ota.html)

本次 WinterBreak2 脚本为了让 Hotfix 能继续安装，曾主动恢复 `otaupd`/`otav3`；这也是为什么不能只凭“某些 WinterBreak 会自动阻止 OTA”就省略安装后的核查。

## 6. 为什么选择“电脑渲染 PNG，Kindle 拉取显示”

早期可以考虑让 Kindle 浏览器直接打开网页仪表盘，但旧 WebKit、TLS、JavaScript、字体和缓存问题会迅速增加维护成本。项目最终采用静态 PNG 拉取，理由是：

- 电脑端可以使用现代 Python、Pillow 和硬件库；
- Kindle 不必执行复杂 JavaScript；
- PNG 的像素布局可完全控制，适合 1072 × 1448 的 PW3；
- FBInk 支持 Kindle 和 PNG 等常见图像格式，能够直接操作电子墨水 framebuffer；
- 失败时仍保留上一帧，不会出现网页半渲染状态。

FBInk 的功能和平台支持见 [NiLuJe/FBInk](https://github.com/NiLuJe/FBInk)。

## 7. 配置 Windows 监控服务

### 7.1 建立 Python 环境

安装 64 位 Python 3.11 或更高版本，在仓库根目录执行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\setup.ps1
```

当前依赖：

```text
Pillow==12.3.0
psutil==7.2.2
```

验证：

```powershell
.\.venv\Scripts\python.exe -c "import PIL, psutil; print('Python dependencies OK')"
```

### 7.2 设置访问令牌

电脑端 `config.toml` 与 Kindle 端 `kindle-extension/kindle-monitor/config.sh` 必须使用同一个随机令牌。不要把项目当前真实令牌复制到公开教程、截图、日志或 Git 仓库。

生成 64 字符随机令牌：

```powershell
$tokenBytes = New-Object byte[] 32
$rng = [Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($tokenBytes)
$rng.Dispose()
$token = (([BitConverter]::ToString($tokenBytes)) -replace '-', '').ToLowerInvariant()
$token
```

电脑端：

```toml
[server]
bind_host = "0.0.0.0"
port = 8765
auth_token = "<生成的长随机令牌>"
sample_interval_seconds = 2.0
codex_interval_seconds = 60.0
amd_sample_interval_seconds = 10.0
```

Kindle 端：

```sh
SERVER_HOST=""
SERVER_PORT=8765
AUTH_TOKEN="<同一个长随机令牌>"
REFRESH_SECONDS=10
FULL_REFRESH_EVERY=180
HIDE_SYSTEM_CHROME=1
```

`SERVER_HOST=""` 是项目后期很重要的改进：Kindle 会自动读取当前 Wi-Fi 默认网关，并把它当作监控电脑。使用 Windows 移动热点时，热点电脑就是网关，因此换电脑或热点 IP 改变后通常不必再改 Kindle 配置。

只有在普通路由器网络、服务器不是默认网关时，才填写固定 IPv4。

### 7.3 传感器第一层：LibreHardwareMonitor

项目中的 `KindleMonitor.SensorBridge.exe` 读取 LibreHardwareMonitor 的 CPU、GPU、主板、存储和网络传感器。官方说明它能读取 Intel/AMD CPU、NVIDIA/AMD/Intel GPU 等硬件；某些传感器需要管理员权限。[LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor)

当前生产文件在：

```text
vendor\librehardwaremonitor\
```

不要只替换一个 `LibreHardwareMonitorLib.dll` 就假定版本升级成功；库的依赖和桥接程序目标框架也要匹配。项目曾测试 nightly，但没有用未经验证的 nightly 覆盖生产版。

### 7.4 安装 PawnIO

当前 LibreHardwareMonitor 的底层硬件访问依赖 PawnIO。项目保留了官方安装包：

```text
请从 PawnIO.Setup 官方发布页下载安装包，不要使用仓库外的未知镜像。
```

本次文件 SHA-256：

```text
1F519A22E47187F70A1379A48CA604981C4FCF694F4E65B734AAA74A9FBA3032
```

安装后必须重启 Windows。若静默安装返回代码 `3010`，它的含义是“安装成功，但需要重启”，不是普通失败；PawnIO 2.2.0 发布说明也明确使用 `ERROR_SUCCESS_REBOOT_REQUIRED` 表示这一状态。[PawnIO 2.2.0 releases](https://github.com/namazso/PawnIO.Setup/releases)

重启后检查：

```powershell
Get-Service PawnIO
```

### 7.5 避坑：Ryzen 5800X 温度、功耗、频率全是 0

本次最花时间的问题不是页面，而是 Ryzen 7 5800X 的底层传感器：

- CPU 负载能显示；
- GPU 温度、功耗、VRAM 正常；
- CPU 温度、Package Power、硬件频率在 LibreHardwareMonitor 中为 0；
- 安装 PawnIO、重启、测试 stable 和 nightly 后仍未完全恢复。

这不是单纯的字段映射错误。LibreHardwareMonitor 社区也记录过 Ryzen 5000 + PawnIO 后温度/频率为 0 的问题，例如 [issue #1875](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/issues/1875) 和 [issue #1937](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/issues/1937)。因此项目加入了第二条只读后备链路。

### 7.6 传感器第二层：AMD Ryzen Master Monitoring SDK

AMD 官方提供 Ryzen Master Monitoring SDK，允许监控工具读取 Ryzen/Threadripper 处理器数据。[AMD Developer Tools](https://www.amd.com/en/developer/browse-by-resource-type/software-tools.html)

本次 SDK 安装后 CLI 位于：

```text
C:\Program Files\AMD\RyzenMasterSDK\AMDRyzenMasterCLI\bin-prebuilt\AMDRyzenMasterCLI.exe
```

项目脚本 `pc-monitor/test-amd-ryzen-master-admin.ps1` 会以只读方式运行 `GetPMTableData`，并解析：

- `GetCurrentTemperature ... Celsius`；
- `PPT Current Value ... W`；
- 各核心 `GetEffectiveFrequency ... MHz` 的平均值。

由于 SDK 需要真正的管理员令牌，直接双击：

```text
start-syswatch.cmd
```

它会请求 UAC，先运行 AMD 只读检测，清理本项目残留 bridge，再用隐藏窗口启动 Python 服务。

诊断文件在：

```text
runtime\amd-metrics-admin.json
runtime\amd-pm-table-admin.txt
```

本次实测最终恢复了 CPU 温度和有效频率，但 `package_power_w` 仍可能为 `null`。这是 SDK 输出不一定包含匹配的 PPT 行，不应伪造一个数字；仪表盘显示 `--W` 才是正确降级行为。

另一个迁移避坑是：当前解析器按本次 SDK 输出格式编写。未来安装新版 SDK 后，如果字段名称改变，要查看原始 PM table 并更新正则，而不是认定 CPU 坏了。

### 7.7 Codex 每周额度

项目通过系统 `PATH` 找到 `codex.exe`，启动 `codex app-server`，再调用 `account/rateLimits/read` 读取当前本地会话的额度快照。当前仪表盘只显示 **Weekly Budget**；原先的 5 小时窗口已经取消，因此不再保留无意义的 Window 2。

新电脑上应重新安装并登录 Codex：

```powershell
where.exe codex
codex login
codex login status
```

不要复制旧电脑的登录凭据。官方参考：[Codex CLI](https://learn.chatgpt.com/docs/codex/cli) 与 [Authentication](https://learn.chatgpt.com/docs/auth)。

`app-server` 的返回结构可能随 Codex 更新变化。如果硬件数据正常而额度区异常，先检查 `codex login status`，再检查 `pc-monitor/kindle_monitor/codex_usage.py` 的解析结构。

## 8. 配置热点与 Windows 防火墙

### 8.1 推荐网络：Windows 移动热点

1. 在 Windows 打开移动热点。
2. 让 Kindle 连接该热点。
3. 调试网络时断开 Kindle USB 数据线，避免设备停留在 USB 磁盘模式。
4. 保持 Kindle `SERVER_HOST=""`。

这样 Kindle 每次都把当前默认网关作为服务地址，不依赖固定的 `192.168.x.x`。这直接解决了“换电脑后热点地址变了怎么办”的迁移问题。

### 8.2 创建最小范围防火墙规则

项目提供 `install-firewall.ps1`。不要把真实 Kindle MAC 写进公开文档。以管理员 PowerShell 执行：

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\install-firewall.ps1 -KindleMac '<KINDLE-MAC>'
```

脚本会从 Windows 邻居表查到 Kindle 当前 IP，再创建只允许该 Kindle 访问当前热点本地地址 TCP 8765 的规则。

如果提示找不到 Kindle：

1. 确认 Kindle 已连接此电脑热点；
2. 拔掉 USB；
3. 在 Kindle 打开一次网页或网络诊断，让邻居表产生记录；
4. 再运行脚本。

## 9. 部署 Kindle SYSWATCH 扩展

### 9.1 目录结构

把电脑中的 `kindle-extension/kindle-monitor` 完整复制到 Kindle，并把 `config.example.sh` 复制为 `config.sh`：

```text
<Kindle盘符>:\extensions\kindle-monitor
```

最终应有：

```text
<Kindle盘符>:\extensions\kindle-monitor\menu.json
<Kindle盘符>:\extensions\kindle-monitor\config.xml
<Kindle盘符>:\extensions\kindle-monitor\config.sh
<Kindle盘符>:\extensions\kindle-monitor\bin\common.sh
<Kindle盘符>:\extensions\kindle-monitor\bin\start.sh
<Kindle盘符>:\extensions\kindle-monitor\bin\run.sh
<Kindle盘符>:\extensions\kindle-monitor\bin\refresh.sh
<Kindle盘符>:\extensions\kindle-monitor\bin\stop.sh
```

所有 `.sh` 文件应使用 LF 行尾。若被 Windows 编辑器改成 CRLF，Kindle shell 可能报莫名其妙的“not found”或无法执行。

### 9.2 确认 FBInk

当前扩展固定调用：

```text
/mnt/us/libkh/bin/fbink
```

本次设备上该路径可用。如果你的设备没有，应从可信的 Kindle/FBInk 发布包安装与设备架构匹配的版本。PW3 5.16.2.1.1 是 soft-float；不要把 hard-float 二进制直接复制过来。

### 9.3 启动

1. 安全弹出 Kindle，拔线。
2. 确认 Kindle 连接 Windows 热点。
3. 在电脑双击 `start-syswatch.cmd`。
4. 电脑浏览器访问 `http://127.0.0.1:8765/healthz`，应返回 `ok`。
5. Kindle 打开 KUAL：

```text
Kindle SYSWATCH → Start monitor
```

扩展会先显示 `SYSWATCH: starting`，等待 KUAL 返回主页，3 秒后开始下载仪表盘。第一次与每 180 次成功刷新使用全刷；普通刷新间隔 10 秒，因此约每 30 分钟做一次全刷以减轻残影。

KUAL 菜单还提供 `Refresh now` 和 `Stop monitor`。停止会恢复 Kindle 原生 UI、允许休眠并回到主页。

## 10. 避坑：SYSWATCH 只停在 starting

`start.sh` 把长期循环放到后台，因此 `SYSWATCH: starting` 本身只是启动提示。如果几秒后仪表盘仍未出现，按下面顺序检查。

### 10.1 先查电脑

```powershell
Get-NetTCPConnection -LocalPort 8765 -State Listen
Invoke-WebRequest http://127.0.0.1:8765/healthz
```

再使用 `config.toml` 中的令牌检查：

```text
http://127.0.0.1:8765/api/status?token=<AUTH_TOKEN>
```

重点看 `cpu_load`、`cpu_temp`、`cpu_power`、`cpu_clock`、`gpu_load`、`gpu_temp` 和 `amd_error`。

### 10.2 再查网络

- Kindle 和电脑是否在同一热点；
- Kindle 是否仍插着 USB；
- 8765 防火墙规则是否创建；
- `SERVER_HOST` 是空字符串还是错误的旧 IP；
- `AUTH_TOKEN` 两端是否完全一致。

### 10.3 最后查 Kindle 日志

停止监控、插入 USB 后查看：

```text
G:\extensions\kindle-monitor\runtime\monitor.log
```

| 现象 | 优先检查 |
| --- | --- |
| `PC OFFLINE` | 服务没启动、热点/防火墙、地址错误 |
| HTTP 403 | 两端令牌不同 |
| 下载文件小于 1 KB | 返回了错误页而非 PNG |
| `fbink: not found` | `/mnt/us/libkh/bin/fbink` 缺失或架构不符 |
| 一直只有 `starting` | 后台脚本没执行、CRLF 行尾、目录错误 |

本项目下载时先写 `dashboard.tmp`，确认文件大于 1 KB 后再原子替换 `dashboard.png`，网络失败不会破坏上一张正常画面。

## 11. 隐藏 Kindle 原生时间和电量栏

只把 PNG 画满全屏并不够。Kindle 的 Pillow UI 会独立绘制左上角时间和右上角电量，应用切换、唤醒或系统事件后还可能再次出现。

当前扩展在每次 FBInk 绘制前都执行：

```sh
lipc-set-prop com.lab126.pillow disableEnablePillow disable
```

停止监控时恢复：

```sh
lipc-set-prop com.lab126.pillow disableEnablePillow enable
```

对应开关是 `HIDE_SYSTEM_CHROME=1`。这个“每帧前再次隐藏”的做法解决了原生时间/电量偶尔重新覆盖仪表盘的问题。不要永久禁用后不恢复，否则退出 SYSWATCH 后 Kindle 原生界面会缺少状态栏。

## 12. 仪表盘设计：真实电子墨水屏和电脑预览不是一回事

项目经历了黑底 HUD、白底复刻、字体增强、线条增强、告警图标和对齐调整。实拍带来的经验比电脑预览更重要。

### 12.1 白底比大面积黑底更稳

黑底模板在显示器上很酷，但 PW3 实拍中大黑块容易显脏、残影明显，也会掩盖细字。最终采用白底、黑色粗线、局部反白状态区。

### 12.2 小字必须比想象中更大更粗

1072 × 1448 的 PNG 缩到 6 英寸屏幕后，普通说明文字很容易糊成灰线。最终处理包括：

- 小字整体加大、加粗；
- 主要边框和分割线显著加粗；
- 关键数据使用大号等宽字；
- 依靠留白分组，不靠极细装饰线。

### 12.3 不要依赖 Emoji 作为状态图标

警告、信号和感叹号在不同字体中基线、字宽、黑白轮廓不一致，实拍会显得错位。最终的磁盘告警和网络状态符号用 Pillow 基础图形自行绘制，而不是依赖 Emoji 字形。

磁盘标签是动态的：

```text
磁盘占用 < 80%  → SYSTEM DISK
磁盘占用 ≥ 80%  → DISK / HIGH + 自绘警告标
```

### 12.4 先保留备份，再做视觉迭代

项目中每个重要改造前都做了时间戳备份，例如：

```text
backups\20260812-222358-black-template
backups\20260812-223405-white-template-before-typography-fix
backups\20260812-224835-before-disk-reset-spacing-fix
backups\20260812-225330-before-heavy-lines-warning-icon
backups\20260812-231822-before-auto-host-chrome
backups\20260813-005200-before-amd-temp-fallback
```

如果新布局“不好看”，直接恢复上一份 `render.py` 和相关配置，比凭记忆反向修改可靠得多。

## 13. 日常使用

启动顺序：

```text
1. Windows 打开移动热点
2. Kindle 连接热点
3. 双击 start-syswatch.cmd
4. KUAL → Kindle SYSWATCH → Start monitor
```

停止时用 `KUAL → Kindle SYSWATCH → Stop monitor`，让扩展恢复状态栏和休眠策略。

主要布局代码：

```text
kindle_monitor\render.py
```

CPU/GPU 型号文字可在 `config.toml` 的 `[dashboard]` 中配置。如果更换硬件，先获取型号：

```powershell
Get-CimInstance Win32_Processor | Select-Object Name
Get-CimInstance Win32_VideoController | Select-Object Name
```

再修改 `render.py` 中相应标签。

## 14. 换电脑迁移

完整步骤见项目中的 [新电脑迁移流程.md](./新电脑迁移流程.md)。核心结论：

- Kindle 不需要重新越狱；
- KUAL、FBInk 和 SYSWATCH 扩展都可以保留；
- 复制 `pc-monitor`，但不要复制旧 `.venv` 和 `runtime`；
- 新电脑重新创建 Python 环境、安装 PawnIO，并重启；
- AMD 电脑安装 Ryzen Master Monitoring SDK；Intel 电脑需要跳过 AMD 强制检测并验证 LHM；
- 新电脑重新执行 `codex login`；
- Kindle 连接新电脑热点，`SERVER_HOST=""` 会自动使用新网关；
- 重新运行防火墙配对脚本；
- 新 CPU/GPU 需要修改型号文字并验证传感器字段。

## 15. 更新、恢复和回退

### 15.1 更新 Kindle 固件前

1. 备份 `documents`、`extensions`、`libkh` 和重要配置。
2. 开启飞行模式。
3. KUAL 中把 Rename OTA Binaries 切到 `Restore`。
4. 确认目标固件仍有越狱/Hotfix 支持。
5. 更新后重新运行或安装 Hotfix，必要时重新安装 KUAL。
6. 一切验证正常后再切回 `Rename`。

### 15.2 回退 Windows 仪表盘

先停止电脑服务，再从对应时间戳目录恢复。不要整目录覆盖不相关文件，优先比较并恢复：

```text
kindle_monitor\render.py
kindle_monitor\sensors.py
config.toml
kindle-extension\kindle-monitor\
```

### 15.3 公开分享项目前先脱敏

至少检查：

```text
config.toml
kindle-extension\kindle-monitor\config.sh
install-firewall.ps1
runtime\
Kindle 网络诊断截图
```

不要发布真实 `AUTH_TOKEN`、Kindle 序列号/DSN、Kindle MAC、Codex 登录凭据、带令牌的完整请求 URL。监控服务器本身已经避免在日志中记录查询字符串，因为 URL 查询中含令牌。

## 16. 故障速查表

| 问题 | 原因/判断 | 处理 |
| --- | --- | --- |
| WinterBreak2 页面显示 308 | 老浏览器不能处理托管重定向 | 使用项目局域网 HTTP 触发脚本 |
| 新 Vercel 地址白屏 | TLS/JS/浏览器兼容问题 | 使用极简本地页 |
| 越狱后要求 Hotfix | 本次 WinterBreak2 版本的正常流程 | 立即安装 Universal Hotfix |
| `Collecting Debug Info` | Kindle 在生成进程 core dump | 可删 KPPMainApp 文档；建 `DISABLE_CORE_DUMP` |
| `;log` 没反应 | 搜索/固件/输入流程未给有效反馈 | 结合完成文本、Hotfix、KUAL 实际功能判断 |
| `No arg passed. Select from mrpi or runme` | 调度脚本缺少模式参数 | 核对 KUAL/MRPI 目录和入口 |
| KUAL 不出现 | 位置、空间、文件名或版本错误 | PEKI 放 `documents`，保证约 220 MB，去掉 `(1)` |
| `SYSWATCH: starting` 后无画面 | PC 服务/网络/令牌/FBInk/CRLF | 按第 10 章逐层排查 |
| HTTP 403 | 两端 `AUTH_TOKEN` 不同 | 同步配置后重启两端 |
| CPU 温度 `--.-°C` | LHM/PawnIO 未读到 Ryzen SMU | 管理员启动，检查 PawnIO 和 AMD SDK JSON |
| CPU PWR 为 `--W` | Ryzen Master 输出未包含可解析 PPT | 保持空值；查看原始 PM table |
| 原生时间/电量重新出现 | Pillow 被系统重新启用 | 每次 FBInk 绘制前重新 disable Pillow |
| 画面残影 | 局部刷新累积 | 保留 10 秒刷新、约 30 分钟一次全刷；必要时适当缩短全刷周期 |
| 换电脑后连不上 | 固定 IP、防火墙或令牌未迁移 | `SERVER_HOST=""` + 新电脑重配防火墙 |

## 17. 参考资料

- [KindleModding — WinterBreak](https://kindlemodding.org/jailbreaking/WinterBreak/)
- [KindleModding — WinterBreak2 GitHub](https://github.com/KindleModding/Winterbreak2)
- [KindleModding — Hotfix](https://kindlemodding.org/jailbreaking/post-jailbreak/setting-up-a-hotfix/)
- [KindleModding — Installing KUAL & MRPI](https://kindlemodding.org/jailbreaking/post-jailbreak/installing-kual-mrpi/)
- [KindleModding — Disabling OTA Updates](https://kindlemodding.org/jailbreaking/post-jailbreak/disable-ota.html)
- [KindleModding — Jailbreak FAQ](https://kindlemodding.org/jailbreaking/jailbreak-faq.html)
- [NiLuJe/FBInk](https://github.com/NiLuJe/FBInk)
- [LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor)
- [PawnIO.Setup releases](https://github.com/namazso/PawnIO.Setup/releases)
- [AMD Ryzen Master Monitoring SDK](https://www.amd.com/en/developer/browse-by-resource-type/software-tools.html)
- [OpenAI Codex CLI](https://learn.chatgpt.com/docs/codex/cli)
- [OpenAI Authentication](https://learn.chatgpt.com/docs/auth)

---

这套方案最值得复用的不是某一张仪表盘图片，而是分层思路：**Kindle 只负责稳定显示，电脑负责采集和渲染；每一层都有独立验证点、日志、后备通道和可回退备份。** 只要保住这条边界，换页面、换电脑甚至换传感器库都不必重新折腾 Kindle 越狱。
