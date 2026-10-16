# agent-model-local 更新日志

本文件统一记录 `agent-model-local` 的功能变更、问题修复、构建验证和服务器部署状态。

- 日期按从新到旧排列，每个日期只使用一个二级标题。
- 同一日期的不同事项使用编号三级标题；事项内部使用四级标题描述根因、修改和验证。
- 同一问题存在多轮定位时按阶段连续记录，并明确后续方案是否取代前一方案。
- 每项记录覆盖最终采用方案、构建环境、部署位置及验证结论。

## 2026-10-16

### 1. 容器用户 HOME 初始化及 sudo/vim 开发环境修复

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
