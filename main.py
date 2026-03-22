import base64
import json
import logging
import os
import re
import time
from pathlib import Path

import ddddocr
import requests
from dotenv import load_dotenv

from utils import normalize_captcha, rm_transparent

load_dotenv(override=True)

BASE_URL = "https://www.mhh1.com"
REQUEST_TIMEOUT = 15
RETRY_COUNT = 3
CAPTCHA_RETRY_COUNT = 5

GET_NONCE_ACTION = "285d6af5ed069e78e04b2d054182dcb5"
GET_CAPTCHA_ACTION = "b9215121b88d889ea28808c5adabbbf5"
LOGIN_ACTION = "0ac2206cd584f32fba03df08b4123264"
SIGN_ACTION = "9f9fa05823795c1c74e8c27e8d5e6930"

USERNAME = os.getenv("USERNAME", "").replace("\ufeff", "").strip()
PASSWORD = os.getenv("PASSWORD", "").replace("\ufeff", "").strip()
PUSH_URL = os.getenv("PUSH_URL", "").strip()
SAVE_CAPTCHA = os.getenv("SAVE_CAPTCHA", "").strip().lower() in {"1", "true", "yes", "on"}

DATA_DIR = Path(os.getenv("DATA_DIR", ".")).expanduser().resolve()
COOKIE_FILE = DATA_DIR / "cookies.json"
CAPTCHA_FILE = DATA_DIR / "captcha.png"
LOG_FILE = DATA_DIR / "logs.txt"

DATA_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    encoding="utf-8",
)


class SignClient:
    def __init__(self):
        self.session = requests.Session()
        self.ocr = ddddocr.DdddOcr(show_ad=False)
        self.headers = {
            "referer": f"{BASE_URL}/",
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/102.0.5005.124 Safari/537.36 Edg/102.0.1245.44"
            ),
        }

    def validate_config(self):
        if not USERNAME or not PASSWORD:
            raise RuntimeError("USERNAME 或 PASSWORD 未配置")

        if not PUSH_URL:
            logging.warning("未配置 PUSH_URL，将跳过推送通知")

    def request(self, method, path, *, expect_json=False, **kwargs):
        url = path if path.startswith("http") else f"{BASE_URL}{path}"
        response = self.session.request(
            method,
            url,
            headers=self.headers,
            timeout=REQUEST_TIMEOUT,
            **kwargs,
        )
        response.raise_for_status()

        if expect_json:
            try:
                return response.json()
            except ValueError as exc:
                raise RuntimeError(f"接口返回的 JSON 无法解析: {url}") from exc

        return response

    def init_session(self):
        logging.info("初始化会话")
        self.request("GET", "/")

    def load_cookie(self):
        try:
            with COOKIE_FILE.open("r", encoding="utf-8") as file:
                cookies = json.load(file)
        except FileNotFoundError:
            logging.info("未找到 cookie 文件，将执行登录流程")
            return False
        except json.JSONDecodeError as exc:
            logging.warning("cookie 文件不是合法 JSON: %s", exc)
            return False
        except OSError as exc:
            logging.warning("读取 cookie 文件失败: %s", exc)
            return False

        self.session.cookies.update(cookies)
        logging.info("已加载本地 cookie: %s", COOKIE_FILE)
        return True

    def save_cookie(self):
        with COOKIE_FILE.open("w", encoding="utf-8") as file:
            json.dump(self.session.cookies.get_dict(), file, ensure_ascii=False, indent=2)
        logging.info("已保存 cookie: %s", COOKIE_FILE)

    def get_nonce(self):
        payload = self.request(
            "GET",
            f"/wp-admin/admin-ajax.php?action={GET_NONCE_ACTION}",
            expect_json=True,
        )

        try:
            nonce = payload["_nonce"]
            logged_in = int(payload["user"]["id"]) != 0
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(f"nonce 接口返回结构异常: {payload}") from exc

        logging.info("获取 nonce 成功，当前登录状态: %s", logged_in)
        return nonce, logged_in

    def get_captcha(self, nonce):
        payload = self.request(
            "GET",
            (
                "/wp-admin/admin-ajax.php"
                f"?_nonce={nonce}"
                f"&action={GET_CAPTCHA_ACTION}"
                "&type=getCaptcha"
            ),
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

        captcha = self.ocr.classification(img_bytes).strip()
        captcha = re.sub(r"\W+", "", captcha)
        logging.info("OCR 识别结果: %s", captcha)

        if not captcha:
            raise RuntimeError("OCR 未识别出验证码")

        return captcha

    def login(self, nonce):
        logging.info("开始登录流程")
        login_url = (
            "/wp-admin/admin-ajax.php"
            f"?_nonce={nonce}"
            f"&action={LOGIN_ACTION}"
            "&type=login"
        )

        for attempt in range(1, CAPTCHA_RETRY_COUNT + 1):
            captcha = self.recognize_captcha(nonce)
            form_data = {
                "email": USERNAME,
                "pwd": PASSWORD,
                "captcha": captcha,
                "type": "login",
            }
            response = self.request("POST", login_url, data=form_data)
            body = response.text.strip()
            logging.info("登录接口返回: %s", body)

            if "success" in body.lower() or "登录成功" in body:
                self.save_cookie()
                logging.info("登录成功")
                return True

            try:
                payload = response.json()
            except ValueError:
                payload = None

            if payload and payload.get("code") == 0:
                self.save_cookie()
                logging.info("登录成功")
                return True

            logging.warning("第 %s 次验证码识别登录失败: %s", attempt, body)
            time.sleep(1)

        logging.error("验证码连续识别失败，登录未成功")
        return False

    def sign(self, nonce):
        payload = self.request(
            "GET",
            (
                "/wp-admin/admin-ajax.php"
                f"?_nonce={nonce}"
                f"&action={SIGN_ACTION}"
                "&type=goSign"
            ),
            expect_json=True,
        )
        msg = payload.get("msg", "未知结果")
        logging.info("签到结果: %s", msg)
        return msg

    def push(self, msg):
        if not PUSH_URL:
            return

        try:
            response = requests.post(
                PUSH_URL,
                data={"title": msg},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            logging.info("推送通知成功")
        except requests.RequestException as exc:
            logging.error("推送通知失败: %s", exc)

    def run(self):
        self.validate_config()
        self.init_session()
        self.load_cookie()

        for attempt in range(1, RETRY_COUNT + 1):
            try:
                nonce, logged_in = self.get_nonce()

                if not logged_in:
                    logging.info("当前未登录，开始尝试登录")
                    if not self.login(nonce):
                        time.sleep(2)
                        continue

                    nonce, logged_in = self.get_nonce()
                    if not logged_in:
                        raise RuntimeError("登录接口返回成功，但会话仍未登录")

                msg = self.sign(nonce)
                self.push(msg)
                return
            except requests.RequestException as exc:
                logging.error("第 %s 次尝试失败，请求异常: %s", attempt, exc)
            except Exception as exc:
                logging.error("第 %s 次尝试失败: %s", attempt, exc)

            time.sleep(2)

        logging.error("连续多次尝试失败，程序退出")


if __name__ == "__main__":
    SignClient().run()
