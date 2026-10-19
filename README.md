# Agent Model Local：领域 RAG 模型微调工程

本工程在单卡 24GB NVIDIA GPU 上，以 **Qwen3-Embedding-0.6B + LoRA** 实现文档输入、数据生成、负样本挖掘、训练、评估、导出和检索验证。所有 Python 依赖、文档转换和 GPU 任务均在官方 PyTorch 基础镜像构建的容器内执行。

部署位置：`192.168.88.91:/home/cdky/workspace/github/agent-model-local`。登录密码不写入工程。

- [使用手册](docs/使用手册.md)：从启动容器到生产数据训练的完整操作。
- [搭建记录](docs/搭建记录.md)：环境、设计依据、构建过程与验收记录。
- [验收报告](docs/验收报告.json)：服务器实测指标、显存、断点恢复与导出一致性证据。
- [数据规范与扩展](docs/数据规范与扩展.md)：数据契约、隔离策略、ReRank/LLM 扩展。

```bash
cd /home/cdky/workspace/github/agent-model-local
bash docker/docker.sh build
bash docker/docker.sh start
# start 初始化后进入容器；输入 exit 返回宿主机，容器继续运行
bash docker/docker.sh exec python -m aml.cli doctor
bash docker/docker.sh exec python -m pytest -q
# 首次运行的独立演示：60 个 PDF/Word/Markdown -> 数据 -> 2 步 LoRA -> 评估 -> 导出
bash docker/docker.sh exec bash scripts/demo.sh
```

演示版本 `demo/v1` 和实验 `lora-v1` 是一次性目录；已有产物时请采用新版本/新实验名，避免误覆盖。服务器上已执行的验收状态以搭建记录为准。

容器入口与 `vision-pipeline/docker/docker.sh` 保持同一风格：`start` 启动、初始化并进入容器，`into`/`shell` 进入已有容器，`exec` 执行单条命令，`logs` 持续跟踪日志。启动会在容器内建立与主机 UID/GID 对应的真实用户、组及标准 `/home/<用户>`，并提供容器内可用的 `sudo`、`vim`；训练仍以普通用户运行，不修改主机账户。镜像和长期容器不设置全局 Hugging Face 缓存目录，下载任务只在各自输出目录内保留局部断点缓存。

Docker 环境创建风格已按 91 服务器上的 `vision-pipeline` 对齐：Compose 使用 host PID/IPC/network、`privileged`、主机 `/dev`/`/media`/X11 挂载及 16GB `shm_size` 配置，`env.sh` 会配置免密 sudo 和宿主机 `kernel.core_pattern`。这是一套面向受信任开发服务器的高权限配置，不应视为安全隔离边界；`GPU_ID` 仍用于 Compose 的 GPU 设备申请，但在 `privileged` 且挂载整个 `/dev` 时不能作为严格的设备隔离。完整影响、可配置参数和跨工程复用规则见[使用手册](docs/使用手册.md)与[搭建记录](docs/搭建记录.md)。

```text
docker/                       Dockerfile、Compose、生命周期脚本、固定直接依赖
configs/embedding/            模型训练配方；复制配置创建独立实验
src/aml/                     共用数据基础设施 + embedding 专用训练/推理
scripts/                     可复用流程编排与混合格式演示
tests/                       数据隔离、篡改检测、挖掘过滤、池化与指标测试
docs/                        中文文档
data/external/<dataset>/      Hugging Face 下载数据与版本记录
data/domains/<domain>/raw/    原始文档（不进入 Git）
data/domains/<domain>/staging/解析文本、待审核查询
data/domains/<domain>/versions/<version>/
  corpus.jsonl               冻结语料、来源、split
  {train,dev,test}.queries.jsonl
  manifest.json              输入及冻结数据 SHA256
  embedding/<mining-run>/     本次挖掘训练集与报告
  reranker/                  ReRank 样本，独立于 embedding
  llm/                       LLM 待标注样本，独立于 embedding
models/base/<model>/          共享只读使用的基础权重及下载 revision
models/exports/<task>/<domain>/<release>/
runs/<task>/<domain>/<model>/<experiment>/
runs/evaluation/<domain>/     检索指标与逐查询结果
logs/                        部署、构建、下载、验收日志
```

当前实现的训练器是 Embedding LoRA；ReRank/LLM 共用文档、下载、版本和数据转换基础设施，专用训练器需后续添加。模板生成的查询是弱标签，仅用于演示或人工编辑起点。正式上线前以人工审核的独立测试集完成质量验收。
