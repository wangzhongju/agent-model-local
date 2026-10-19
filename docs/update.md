# agent-model-local 更新日志

本文件统一记录 `agent-model-local` 的功能变更、问题修复、构建验证和服务器部署状态。

- 日期按从新到旧排列，每个日期只使用一个二级标题。
- 同一日期的不同事项使用编号三级标题；事项内部使用四级标题描述根因、修改和验证。
- 同一问题存在多轮定位时按阶段连续记录，并明确后续方案是否取代前一方案。
- 每项记录覆盖最终采用方案、构建环境、部署位置及验证结论。

## 2026-10-16

### 1. 容器用户 HOME 初始化及 sudo/vim 开发环境修复

> 本项保留中间修复过程。其持久化 HOME、受限 capability 和禁用 host/privileged 的方案，已被同日第 2 项的最终统一方案取代。

#### 根因

- 容器 HOME 固定在项目挂载的 `/workspace/.cache/home`。目录已存在时，旧 `ensure_user` 使用 `useradd --no-create-home`，因此 `/etc/skel` 中的 `.bashrc`、`.profile` 等默认文件不会被复制；后续 `append_once` 只创建并写入 PS1/XDG 两行。问题不是写覆盖，而是持久化 HOME 跳过了系统骨架初始化。
- 缺少标准 `.bashrc` 后，`dircolors` 和 `alias ls='ls --color=auto'` 不存在，终端中的文件统一显示为白色；shell 环境也只剩两条项目配置。
- 原镜像未安装 `sudo` 和 `vim`，Compose 同时设置 `no-new-privileges` 且只提供 HOME 初始化能力；单纯安装 sudo 仍不能让普通容器用户执行提权命令。

#### 修改

- `docker/env.sh` 增加 `seed_user_home`：统一在账户创建后从 `/etc/skel` 补齐缺失文件；对旧版“仅 PS1/XDG 两行”的 `.bashrc` 自动恢复镜像模板，再幂等追加项目配置。含其他自定义内容的现有 `.bashrc` 不覆盖。
- Dockerfile 固定安装 `sudo` 和完整版 `vim`；`configure_sudo` 使用 `visudo` 校验后生成权限 0440 的 `/etc/sudoers.d/agent-model-user`，映射用户可在容器内免密 sudo。
- Compose 继续 `cap_drop: ALL`，只加入 `AUDIT_WRITE/CHOWN/DAC_OVERRIDE/FOWNER/SETGID/SETUID`；普通训练进程保持 `CapEff=0`。训练容器移除会阻止 setuid sudo 的 `no-new-privileges`，但仍不启用 privileged、主机 PID/IPC 或系统目录挂载；下载容器的限制不变。
- 账户回归脚本新增旧 HOME 复现、标准 shell 文件、彩色 ls、sudo/vim、sudoers 和重复初始化哈希检查；README、使用手册和搭建记录同步更新。

#### 验证与部署

- 在 `192.168.88.91:/home/cdky/workspace/github/agent-model-local` 完成镜像重建和主容器重建；最终镜像 ID 为 `sha256:af89e083503dbe1c4cbdb5630905777d544a82a853467d526cb453a5555ceb24`。
- 实际持久化 HOME 的 `.bashrc` 从 2 行恢复为 119 行；`.profile`、自定义彩色 PS1、`XDG_RUNTIME_DIR` 和 `ls --color=auto` 均存在。`sudo -n id -u` 输出 0，sudo 1.9.9 和 vim 8.2 可用。
- `scripts/check_container_accounts.sh` 隔离回归通过；GPU doctor 确认 RTX 4090 D、CUDA 12.6 和 BF16 正常；项目测试 `7 passed in 9.55s`。主机 `/etc/passwd`、`/etc/group` 前后摘要一致。
- 构建、启动、隔离回归、运行时、交互 shell、doctor 和 pytest 日志保存在服务器 `logs/container-devtools-20261016/`。

### 2. Docker 环境创建风格与 vision-pipeline 最终同步

#### 背景与取代关系

- 用户在逐项对比 `vision-pipeline` 后完成 Compose 调整；本轮以当前工程文件和提交 `1bcaada` 为事实基线，同步 README、使用手册和搭建记录。
- 当前方案取代第 1 项关于 `/workspace/.cache/home`、`seed_user_home`、`cap_drop: ALL`、禁用 privileged/host PID/IPC 以及 core_pattern 不影响宿主机的描述。旧内容作为定位历史保留，不再代表现行配置。

#### 修改

- `docker.sh` 的函数划分、命令分发、Compose 生命周期、root 初始化与普通用户进入方式已和参考工程对齐；仅保留工程/镜像命名、基础镜像和 GPU 参数等必要差异。
- `env.sh` 改用 `useradd --create-home` 的标准 `/home/<用户>`，沿用参考工程的账户、sudo/video、PS1、vim、pip、免密 sudo 和 core pattern 流程；删除项目级 Ultralytics/Hugging Face 缓存创建与 `.cache` 递归归属操作。
- Dockerfile 保留 RAG 所需 PyTorch/CUDA、OCR 和固定 Python 依赖，同时按参考风格安装 sudo、vim、curl、git；不引入 RKNN 工具链。
- Compose 启用 host PID/IPC/network、privileged、TTY、自动重启、设备/媒体/X11/时区挂载和 16GB shm 配置。保留 `GPU_ID`、RAG 环境变量和 `init: true`，不复制 RKNN、YOLO/Ultralytics 配置。
- Dockerfile、Compose 和 `env.sh` 均不覆盖 `HOME` 或 `HF_HOME`。HOME 由容器账户解析；模型和数据下载缓存限定在各自输出目录，不以全局变量改变框架缓存行为。
- 文档新增风险边界和可复用同步清单：privileged 容器不作为安全隔离；host IPC 下实际使用主机 `/dev/shm`；`GPU_ID` 在整个 `/dev` 已挂载时不是严格隔离；`setup_core_pattern` 会修改宿主机级内核设置。

#### 验证与部署

- 服务器位置仍为 `192.168.88.91:/home/cdky/workspace/github/agent-model-local`，本轮核验时工作区干净且本地/服务器均指向提交 `1bcaada`。
- 脚本语法和 Compose 渲染通过；运行容器实测 `Privileged=true`、PID/IPC/network 均为 host、`ShmSize=17179869184`、用户 `1000:1000`、hostname `agent-model-local`、restart `unless-stopped`，挂载与 Compose 声明一致。
- 用户 `cdky` 的 HOME 为 `/home/cdky`，属于 sudo/video 组；sudo、vim、curl、git 可用，免密 sudo 返回 root。普通用户进程 `CapPrm=0`、`CapEff=0`，但 `CapBnd` 完整且 `NoNewPrivs=0`，符合当前高权限开发容器模型。
- 宿主机与容器的 `kernel.core_pattern` 均为 `/workspace/data/core/core_%e.%p`；账户幂等/冲突回归通过，`pip check` 无冲突。doctor 确认 PyTorch 2.7.1+cu126、CUDA 12.6、RTX 4090 D 和 BF16 正常，项目测试 `8 passed in 9.26s`。
- 本轮只做环境和回归检查，没有重新训练或改写既有验收产物。后续工程复用时应先区分通用创建风格与业务差异，再按“静态解析—账户回归—HostConfig—依赖/GPU—项目测试—文档”顺序验收。
