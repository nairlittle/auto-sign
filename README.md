# auto-sign

使用 `ddddocr` 自动识别验证码的签到脚本，支持本地运行和 Linux Docker 部署。

## Files

- `main.py`: 签到主程序
- `utils.py`: 验证码图片预处理
- `requirements.txt`: Python 依赖
- `Dockerfile`: Docker 构建文件
- `deploy.sh`: Linux 服务器更新镜像并安装定时任务的脚本
- `.env.example`: 环境变量模板

## Environment

复制模板并填写配置：

```bash
cp .env.example .env
```

示例：

```env
USERNAME=your_account
PASSWORD=your_password
PUSH_URL=
SAVE_CAPTCHA=false
DATA_DIR=/data
```

说明：

- `USERNAME`: 登录账号
- `PASSWORD`: 登录密码
- `PUSH_URL`: 推送通知地址，可留空
- `SAVE_CAPTCHA`: 是否保存验证码图片用于排查
- `DATA_DIR`: 运行数据目录，保存 `cookies.json`、`logs.txt`、`captcha.png`

本地直接运行时，建议改成：

```env
DATA_DIR=.
```

## Local Run

安装依赖：

```bash
pip install -r requirements.txt
```

运行：

```bash
python main.py
```

## Docker Run

构建镜像：

```bash
docker build -t auto-sign:latest .
```

运行容器：

```bash
docker run --rm --env-file .env -v "$(pwd)/data:/data" auto-sign:latest
```

如果使用上面的命令，请把 `.env` 里的 `DATA_DIR` 设置为：

```env
DATA_DIR=/data
```

## Linux Server Layout

推荐目录结构：

```text
/opt/auto-sign/app
/opt/auto-sign/data
```

首次部署：

```bash
mkdir -p /opt/auto-sign
cd /opt/auto-sign
git clone <your-repo-url> app
mkdir -p data
cp app/.env.example data/.env
```

编辑 `/opt/auto-sign/data/.env`：

```env
USERNAME=your_account
PASSWORD=your_password
PUSH_URL=
SAVE_CAPTCHA=false
DATA_DIR=/data
```

## Deploy

给脚本执行权限：

```bash
chmod +x deploy.sh
```

默认部署：

```bash
./deploy.sh
```

脚本会执行：

- `git pull --ff-only`
- `docker build`
- 安装一条每天 `08:30` 执行的 `crontab`

等价于默认使用：

- `APP_DIR=/opt/auto-sign/app`
- `DATA_DIR=/opt/auto-sign/data`
- `IMAGE_NAME=auto-sign:latest`
- `CRON_SCHEDULE=30 8 * * *`

也可以自定义：

```bash
./deploy.sh /srv/auto-sign/app /srv/auto-sign/data
```

或：

```bash
APP_DIR=/srv/auto-sign/app DATA_DIR=/srv/auto-sign/data ./deploy.sh
```

## Update

服务器更新后重新安装定时任务：

```bash
cd /opt/auto-sign/app
./deploy.sh
```

查看当前定时任务：

```bash
crontab -l
```

查看执行日志：

```bash
tail -f /opt/auto-sign/data/cron.log
```

## Git

建议提交这些文件：

- `README.md`
- `Dockerfile`
- `deploy.sh`
- `main.py`
- `utils.py`
- `requirements.txt`
- `.gitignore`
- `.env.example`
- `pyproject.toml`
- `uv.lock`

不要提交：

- `.env`
- `data/`
- `cookies.json`
- `logs.txt`
- `captcha.png`
- `__pycache__/`
- `.venv/`
- `.idea/`
