import base64
import json
import logging
import os
import re
import time
from pathlib import Path

import ddddocr
from curl_cffi import requests
from dotenv import load_dotenv

from utils import normalize_captcha, rm_transparent

load_dotenv(override=True)

BASE_URL = "https://www.mhh1.com"
AJAX_PATH = "/wp-admin/admin-ajax.php"
REQUEST_TIMEOUT = 15
RETRY_COUNT = 3
CAPTCHA_RETRY_COUNT = 5
IMPERSONATE = "chrome136"
TRUTHY = {"1", "true", "yes", "on"}

NONCE_ACTION = "285d6af5ed069e78e04b2d054182dcb5"
NONCE_QUERY = (
    f"?action={NONCE_ACTION}"
    "&d6ca819426678dab7a26ecb2802d8aec%5Btype%5D=checkUnread"
    "&6f05c9bced69c22452fcd115e6fc4838%5Btype%5D=getHomepagePosts"
)
CAPTCHA_ACTION = "b9215121b88d889ea28808c5adabbbf5"
LOGIN_ACTION = "0ac2206cd584f32fba03df08b4123264"
SIGN_ACTION = "9f9fa05823795c1c74e8c27e8d5e6930"

USERNAME = os.getenv("USERNAME", "").replace("\ufeff", "").strip()
PASSWORD = os.getenv("PASSWORD", "").replace("\ufeff", "").strip()
PUSH_URL = os.getenv("PUSH_URL", "").strip()
PROXY_URL = os.getenv("PROXY_URL", "").strip()
SAVE_CAPTCHA = os.getenv("SAVE_CAPTCHA", "").strip().lower() in TRUTHY
CONSOLE_LOG = os.getenv("CONSOLE_LOG", "").strip().lower() in TRUTHY

DATA_DIR = Path(os.getenv("DATA_DIR", ".")).expanduser().resolve()
COOKIE_FILE = DATA_DIR / "cookies.json"
CAPTCHA_FILE = DATA_DIR / "captcha.png"
LOG_FILE = DATA_DIR / "logs.txt"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/146.0.0.0 Safari/537.36"
)

BASE_HEADERS = {
    "accept-language": "zh-CN,zh;q=0.9",
    "user-agent": USER_AGENT,
    "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}

DOCUMENT_HEADERS = {
    **BASE_HEADERS,
    "accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8,"
        "application/signed-exchange;v=b3;q=0.7"
    ),
    "priority": "u=0, i",
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
}

AJAX_HEADERS = {
    **BASE_HEADERS,
    "accept": "*/*",
    "priority": "u=1, i",
    "referer": f"{BASE_URL}/",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
}

DATA_DIR.mkdir(parents=True, exist_ok=True)

handlers = [logging.FileHandler(LOG_FILE, encoding="utf-8")]
if CONSOLE_LOG:
    handlers.append(logging.StreamHandler())

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=handlers,
)
logger = logging.getLogger(__name__)


class SignClient:
    def __init__(self):
        self.session = requests.Session()
        if PROXY_URL:
            self.session.proxies.update({"http": PROXY_URL, "https": PROXY_URL})
        self.ocr = ddddocr.DdddOcr(show_ad=False)

    def validate_config(self):
        if not USERNAME or not PASSWORD:
            raise RuntimeError("USERNAME 或 PASSWORD 未配置")
        if not PUSH_URL:
            logger.warning("未配置 PUSH_URL，将跳过推送通知")
        if PROXY_URL:
            logger.info("已启用代理: %s", PROXY_URL)

    def request(self, method, path, *, headers=None, expect_json=False, **kwargs):
        url = path if path.startswith("http") else f"{BASE_URL}{path}"
        request_kwargs = {
            "headers": dict(headers or AJAX_HEADERS),
            "timeout": REQUEST_TIMEOUT,
            "impersonate": IMPERSONATE,
            **kwargs,
        }

        logger.info("请求 %s %s", method, url)
        response = self.session.request(method, url, **request_kwargs)
        logger.info("响应 %s %s -> %s", method, url, response.status_code)

        if response.status_code == 403:
            self.raise_forbidden(url, response.text)

        response.raise_for_status()
        if not expect_json:
            return response

        try:
            return response.json()
        except ValueError as exc:
            raise RuntimeError(f"接口返回的 JSON 无法解析: {url}") from exc

    @staticmethod
    def raise_forbidden(url, text):
        preview = text.strip().replace("\n", " ")[:300]
        if "当前区域禁止访问" in text:
            raise RuntimeError(
                f"请求被服务器拒绝(403): {url} | 当前区域禁止访问，请更换服务器出口 IP 或配置 PROXY_URL"
            )
        if "Just a moment..." in text or "cf-browser-verification" in text:
            raise RuntimeError(f"请求被服务器拒绝(403): {url} | 命中了 Cloudflare 挑战，请更换代理线路")
        raise RuntimeError(f"请求被服务器拒绝(403): {url} | {preview}")

    @staticmethod
    def ajax_path(action, nonce=None, request_type=None, extra_query=""):
        parts = []
        if nonce is not None:
            parts.append(f"_nonce={nonce}")
        parts.append(f"action={action}")
        if request_type is not None:
            parts.append(f"type={request_type}")
        if extra_query:
            parts.append(extra_query.lstrip("&?"))
        return f"{AJAX_PATH}?{'&'.join(parts)}"

    def init_session(self):
        logger.info("初始化会话")
        self.request("GET", "/", headers=DOCUMENT_HEADERS)

    def load_cookie(self):
        try:
            cookies = json.loads(COOKIE_FILE.read_text(encoding="utf-8"))
        except FileNotFoundError:
            logger.info("未找到 cookie 文件，将执行登录流程")
            return False
        except json.JSONDecodeError as exc:
            logger.warning("cookie 文件不是合法 JSON: %s", exc)
            return False
        except OSError as exc:
            logger.warning("读取 cookie 文件失败: %s", exc)
            return False

        self.session.cookies.update(cookies)
        logger.info("已加载本地 cookie: %s", COOKIE_FILE)
        return True

    def save_cookie(self):
        COOKIE_FILE.write_text(
            json.dumps(self.session.cookies.get_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("已保存 cookie: %s", COOKIE_FILE)

    def get_nonce(self):
        payload = self.request(
            "GET",
            f"{AJAX_PATH}{NONCE_QUERY}",
            headers=AJAX_HEADERS,
            expect_json=True,
        )

        try:
            nonce = payload["_nonce"]
            user = payload["user"]
            user_id = int(user.get("id") or 0)
            logged_in = bool(user.get("isLoggedIn")) or user_id != 0
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(f"nonce 接口返回结构异常: {payload}") from exc

        logger.info("获取 nonce 成功，当前登录状态: %s", logged_in)
        return nonce, logged_in

    def get_captcha(self, nonce):
        payload = self.request(
            "GET",
            self.ajax_path(CAPTCHA_ACTION, nonce=nonce, request_type="getCaptcha"),
            headers=AJAX_HEADERS,
            expect_json=True,
        )

        try:
            return payload["data"]["imgData"]
        except (KeyError, TypeError) as exc:
            raise RuntimeError(f"验证码接口返回结构异常: {payload}") from exc

    def recognize_captcha(self, nonce):
        img_base64 = self.get_captcha(nonce)
        if "," in img_base64:
            _, img_base64 = img_base64.split(",", 1)

        try:
            img_bytes = base64.b64decode(img_base64)
        except ValueError as exc:
            raise RuntimeError("验证码图片不是合法的 base64 数据") from exc

        img_bytes = normalize_captcha(rm_transparent(img_bytes))
        if SAVE_CAPTCHA:
            CAPTCHA_FILE.write_bytes(img_bytes)

        captcha = re.sub(r"\W+", "", self.ocr.classification(img_bytes).strip())
        logger.info("OCR 识别结果: %s", captcha)
        if not captcha:
            raise RuntimeError("OCR 未识别出验证码")
        return captcha

    def login(self, nonce):
        logger.info("开始登录流程")
        login_path = self.ajax_path(LOGIN_ACTION, nonce=nonce, request_type="login")
        login_headers = {
            **AJAX_HEADERS,
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        }

        for attempt in range(1, CAPTCHA_RETRY_COUNT + 1):
            response = self.request(
                "POST",
                login_path,
                headers=login_headers,
                data={
                    "email": USERNAME,
                    "pwd": PASSWORD,
                    "captcha": self.recognize_captcha(nonce),
                    "type": "login",
                },
            )
            body = response.text.strip()
            logger.info("登录接口返回: %s", body)

            try:
                payload = response.json()
            except ValueError:
                payload = None

            if "success" in body.lower() or "登录成功" in body or (payload and payload.get("code") == 0):
                self.save_cookie()
                logger.info("登录成功")
                return True

            logger.warning("第 %s 次验证码识别登录失败: %s", attempt, body)
            time.sleep(1)

        logger.error("验证码连续识别失败，登录未成功")
        return False

    def sign(self, nonce):
        payload = self.request(
            "GET",
            self.ajax_path(SIGN_ACTION, nonce=nonce, request_type="goSign"),
            headers=AJAX_HEADERS,
            expect_json=True,
        )
        msg = payload.get("msg", "未知结果")
        logger.info("签到结果: %s", msg)
        return msg

    def push(self, msg):
        if not PUSH_URL:
            return

        try:
            response = requests.post(
                PUSH_URL,
                data={"title": msg},
                timeout=REQUEST_TIMEOUT,
                impersonate=IMPERSONATE,
            )
            response.raise_for_status()
            logger.info("推送通知成功")
        except Exception as exc:
            logger.error("推送通知失败: %s", exc)

    def run(self):
        logger.info("脚本启动")
        logger.info("HTTP 客户端: %s", requests.__name__)
        logger.info("数据目录: %s", DATA_DIR)

        self.validate_config()
        self.load_cookie()
        self.init_session()

        for attempt in range(1, RETRY_COUNT + 1):
            try:
                logger.info("开始第 %s 次尝试", attempt)
                nonce, logged_in = self.get_nonce()

                if not logged_in:
                    logger.info("当前未登录，开始尝试登录")
                    if not self.login(nonce):
                        time.sleep(2)
                        continue

                    nonce, logged_in = self.get_nonce()
                    if not logged_in:
                        raise RuntimeError("登录接口返回成功，但会话仍未登录")

                msg = self.sign(nonce)
                self.push(msg)
                logger.info("执行完成: %s", msg)
                return
            except Exception as exc:
                logger.error("第 %s 次尝试失败: %s", attempt, exc)
                time.sleep(2)

        logger.error("连续多次尝试失败，程序退出")


if __name__ == "__main__":
    SignClient().run()
