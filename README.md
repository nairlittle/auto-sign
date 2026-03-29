# auto-sign

使用 `curl_cffi` 和 `ddddocr` 自动完成萌幻之乡签到。

## 项目文件

- `main.py`: 主程序
- `utils.py`: 验证码图片预处理
- `requirements.txt`: Python 依赖
- `Dockerfile`: Docker 镜像构建文件
- `deploy.sh`: Linux 服务器部署脚本
- `.env.example`: 环境变量模板

## 环境变量

先复制模板：

```bash
cp .env.example .env
```

示例：

```env
USERNAME=your_account
PASSWORD=your_password
PUSH_URL=
SAVE_CAPTCHA=false
PROXY_URL=
CONSOLE_LOG=false
DATA_DIR=/data
```

说明：

- `USERNAME`: 登录账号
- `PASSWORD`: 登录密码
- `PUSH_URL`: 推送通知地址，可留空
- `SAVE_CAPTCHA`: 是否保存验证码图片，便于排查
- `PROXY_URL`: 代理地址。访问站点通常需要
- `CONSOLE_LOG`: 是否同时输出到控制台，默认 `false`
- `DATA_DIR`: 运行数据目录，保存 `cookies.json`、`logs.txt`、`captcha.png`

本地运行时建议设置：

```env
DATA_DIR=.
```

## 本地运行

安装依赖：

```bash
pip install -r requirements.txt
```

执行：

```bash
python main.py
```

## Docker 运行

构建镜像：

```bash
docker build -t auto-sign:latest .
```

运行容器：

```bash
docker run --rm --env-file .env -v "$(pwd)/data:/data" auto-sign:latest
```

如果使用容器运行，请把 `.env` 里的 `DATA_DIR` 设置为：

```env
DATA_DIR=/data
```

## 服务器部署

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

然后编辑：

```text
/opt/auto-sign/data/.env
```

执行部署：

```bash
cd /opt/auto-sign/app
bash deploy.sh
```

脚本会执行这些操作：

- `git pull --ff-only`
- `docker build`
- 安装一条每天 `08:30` 执行的 `crontab`

## 更新说明

需要重新部署时，执行：

```bash
cd /opt/auto-sign/app
bash deploy.sh
```

如果只修改了 `/opt/auto-sign/data/.env`，不需要重新部署，下一次定时任务会直接使用新的环境变量。

如果删除了 `cookies.json`，脚本会在下一次运行时重新登录。
