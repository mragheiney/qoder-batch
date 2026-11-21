import base64, json, os, random, re, subprocess, sys, time
import websocket, requests
from PIL import Image
from io import BytesIO
from captcha_recognizer.slider import Slider

APP_PORT = 9224
CHR_PORT = 9225
A, B = 0.0769, 0.003552
EMAIL = os.environ["QE"]; PASSWORD = os.environ["QP"]

class CDP:
    def __init__(self, port):
        self.port = port
        t = requests.get(f"http://127.0.0.1:{port}/json", timeout=10).json()
        self.page = next(x for x in t if x.get("type") == "page" and x.get("url"))
        self.ws = websocket.create_connection(f'ws://127.0.0.1:{port}/devtools/page/{self.page["id"]}', timeout=30, suppress_origin=True)
        self.seq = 0
    def send(self, method, params=None):
        self.seq += 1
        self.ws.send(json.dumps({"id": self.seq, "method": method, "params": params or {}}))
        while True:
            d = json.loads(self.ws.recv())
            if d.get("id") == self.seq:
                return d.get("result", {})
    def ev(self, expr):
        r = self.send("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True, "userGesture": True})
        return r.get("result", {}).get("value")
    def focus(self):
        try:
            self.send("Page.bringToFront")
            self.send("Browser.grantPermissions", {"permissions": ["clipboardReadWrite", "clipboardSanitizedWrite", "clipboard-read", "clipboard-write"]})
        except Exception:
            pass
    def shot(self, clip=None):
        p = {"format": "png"}
        if clip: p["clip"] = {**clip, "scale": 2}
        import base64 as b64
        return b64.b64decode(self.send("Page.captureScreenshot", p)["data"])

def solve_slider(cdp, img_el_id="aliyunCaptcha-img"):
    geo = json.loads(cdp.ev(f'''(() => {{
      let e = document.getElementById("{img_el_id}");
      if (!e) {{ let f=null; const deep=(r)=>r.querySelectorAll("*").forEach(x=>{{if(!f&&x.id==="{img_el_id}")f=x; if(x.shadowRoot)deep(x.shadowRoot);}}); deep(document); e=f; }}
      if (!e) return null;
      const r = e.getBoundingClientRect();
      return JSON.stringify([r.x, r.y, r.width, r.height]);
    }})()'''))
    if not geo: return False
    x, y, w, h = geo
    png = cdp.shot({"x": x, "y": y, "width": w, "height": h})
    import cv2, numpy as np
    img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
    r = Slider().identify(img[:, :, ::-1])
    box, conf = r[0], float(r[1])
    if conf < 0.3: return False
    target = float(box[0]) / 2.0
    disc = A * A + 4 * B * target
    D = (-A + disc ** 0.5) / (2 * B)
    sx, sy = x + 20, y + 208 + 20
    sgeo = json.loads(cdp.ev('''(() => { let e=document.getElementById("aliyunCaptcha-sliding-slider"); if(!e){let f=null;const d=(r)=>r.querySelectorAll("*").forEach(x=>{if(!f&&x.id==="aliyunCaptcha-sliding-slider")f=x; if(x.shadowRoot)d(x.shadowRoot);}); d(document); e=f;} if(!e) return null; const r=e.getBoundingClientRect(); return JSON.stringify([r.x,r.y,r.width,r.height]); })()'''))
    if not sgeo: return False
    sx, sy = sgeo[0] + sgeo[2]/2, sgeo[1] + sgeo[3]/2
    cdp.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": sx-70, "y": sy+10, "button": "none"})
    time.sleep(0.15)
    cdp.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": sx, "y": sy, "button": "none"})
    time.sleep(0.25)
    cdp.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": sx, "y": sy, "button": "left", "buttons": 1, "clickCount": 1})
    time.sleep(0.1)
    n = 40
    for i in range(1, n+1):
        t = i / n
        p = 1 - (1 - t) ** 2.3
        cx, cy = sx + D*p + random.uniform(-0.7, 0.7), sy + random.uniform(-2, 2)
        cdp.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": cx, "y": cy, "button": "left", "buttons": 1})
        time.sleep(random.uniform(0.008, 0.03))
    cdp.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": sx + D - 1.6, "y": sy, "button": "left", "buttons": 1})
    time.sleep(0.09)
    cdp.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": sx + D, "y": sy, "button": "left", "buttons": 1})
    time.sleep(0.15)
    cdp.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": sx + D, "y": sy, "button": "left", "buttons": 0, "clickCount": 1})
    return True

def wait_captcha(cdp, timeout=25):
    for _ in range(timeout):
        t = cdp.ev("document.body.innerText")
        if t and ("安全验证" in t or "拖动滑块" in t):
            return True
        time.sleep(1)
    return False

def chrome_login_and_authorize(signin_url):
    chro = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    subprocess.Popen([chro, "--headless=new", f"--remote-debugging-port={CHR_PORT}",
                      f"--user-data-dir={os.environ['TEMP']}\\ghc", "--no-first-run",
                      "--window-size=1400,950", "about:blank"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(6)
    c = CDP(CHR_PORT)
    c.send("Page.navigate", {"url": "https://qoder.com/users/sign-in?product=ide"})
    time.sleep(8)
    c.ev('''(() => {
      const el = document.querySelector("input[type=email], input[name=email], input[placeholder*='邮箱'], input[name='user[email]']");
      if (!el) return "NF";
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(el, arguments_qe);
      el.dispatchEvent(new Event("input", {bubbles:true}));
      return "OK";
    })()'''.replace("arguments_qe", json.dumps(EMAIL)))
    time.sleep(1)
    c.ev('''(() => { const b=[...document.querySelectorAll("button")].find(e=>(e.textContent||"").replace(/\\s+/g,"")==="继 续"); if(b) b.click(); return "C"; })()''')
    time.sleep(4.5)
    c.ev('''(() => {
      const els = [...document.querySelectorAll("input[type=password]")].filter(e=>e.offsetParent!==null);
      const el = els[els.length-1];
      if (!el) return "NF";
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(el, arguments_qp);
      el.dispatchEvent(new Event("input", {bubbles:true}));
      return "OK";
    })()'''.replace("arguments_qp", json.dumps(PASSWORD)))
    time.sleep(1)
    c.ev('''(() => { const b=[...document.querySelectorAll("button")].filter(e=>(e.textContent||"").replace(/\\s+/g,"")==="登录"&&e.offsetParent!==null); if(b.length) b[b.length-1].click(); return "C"; })()''')
    time.sleep(6)
    for attempt in range(3):
        if wait_captcha(c, 20):
            c.ev('''(() => { const els=[...document.querySelectorAll("*")].filter(e=>["BUTTON","DIV","SPAN","A","P"].includes(e.tagName)&&(e.textContent||"").replace(/\\s+/g,"")==="点击开始验证"&&e.children.length<=1); if(els.length) els[els.length-1].click(); return "C"; })()''')
            time.sleep(5)
            if solve_slider(c):
                time.sleep(6)
        t = c.ev("document.body.innerText") or ""
        if "个人中心" in t or "profile" in (c.page.get("url") or "") or "安全验证" not in t and "登录" not in t:
            break
    cur = c.page.get("url") or ""
    c.send("Page.navigate", {"url": signin_url})
    time.sleep(8)
    c.ev('''(() => { const b=[...document.querySelectorAll("button")].find(e=>(e.textContent||"").replace(/\\s+/g,"")==="继续登录"); if(b) b.click(); return "C"; })()''')
    time.sleep(6)
    return True

def main():
    result = {"ok": False, "email": EMAIL, "steps": []}
    try:
        time.sleep(5)
        app = CDP(APP_PORT)
        result["steps"].append("app-cdp")
        for _ in range(10):
            t = app.ev("document.body.innerText") or ""
            if "Log in" in t: break
            time.sleep(3)
        app.ev('''(() => { const b=[...document.querySelectorAll("button,a,[role=button]")].find(e=>(e.textContent||"").trim()==="Log in immediately"); if(b) b.click(); return "C"; })()''')
        try:
            open("app-welcome.png", "wb").write(app.shot())
        except Exception:
            pass
        time.sleep(6)
        # Network 嗅探 device flow URL（App 内部 device/code 请求的响应里有 verification_uri）
        app.send("Network.enable")
        url = None
        deadline = time.time() + 25
        while time.time() < deadline and not url:
            try:
                app.ws.settimeout(3)
                d = json.loads(app.ws.recv())
                m = d.get("method", "")
                if m == "Network.responseReceived":
                    u = d["params"]["response"]["url"]
                    if any(k in u for k in ("device", "oauth", "sign-in", "login")) and "qoder" in u:
                        rid = d["params"]["requestId"]
                        try:
                            body = app.send("Network.getResponseBody", {"requestId": rid})
                            txt = body.get("body", "")
                            j = json.loads(txt) if txt.strip().startswith("{") else {}
                            for key in ("verification_uri_complete", "verification_url", "verification_uri", "signInUrl", "url"):
                                v = j.get(key) or (j.get("data") or {}).get(key) if isinstance(j.get("data"), dict) else j.get(key)
                                if v and str(v).startswith("http"):
                                    url = v; break
                        except Exception:
                            pass
                elif m == "Network.requestWillBeSent":
                    u = d["params"]["request"]["url"]
                    if u.startswith("https://qoder.com/device/"):
                        url = u
            except websocket.WebSocketTimeoutException:
                pass
            except Exception:
                pass
        app.ws.settimeout(30)
        if not url:
            # 系统剪贴板直读（App Copy 按钮写的是系统剪贴板）
            try:
                open("app-waiting.png", "wb").write(app.shot())
            except Exception:
                pass
            result["diag_waiting_text"] = (app.ev("document.body.innerText") or "").replace("\n", " ")[:200]
            result["diag_copy_click"] = app.ev('''(() => { const b=[...document.querySelectorAll("button")].find(e=>(e.textContent||"").includes("Copy sign-in link")); if(!b) return "NO_BTN"; b.click(); return "CLICKED"; })()''')
            time.sleep(2)
            import ctypes
            clip = None
            try:
                ok_open = ctypes.windll.user32.OpenClipboard(0)
                h2 = ctypes.windll.user32.GetClipboardData(13)  # CF_UNICODETEXT
                if h2:
                    p = ctypes.windll.kernel32.GlobalLock(h2)
                    clip = ctypes.wstring_at(p)
                    ctypes.windll.kernel32.GlobalUnlock(h2)
                ctypes.windll.user32.CloseClipboard()
            except Exception as e:
                clip = "CLIP_ERR:" + repr(e)
            result["diag_clipboard"] = (clip or "EMPTY")[:120]
            if clip and str(clip).startswith("http"):
                url = clip
        if not url or not str(url).startswith("http"):
            app.focus()
            url = app.ev('''navigator.clipboard.readText().catch(e => "ERR:" + e.message)''')
        if not url or not str(url).startswith("http"):
            raise RuntimeError("no signin url: " + str(url))
        result["signin_url"] = url[:60] + "..."
        result["steps"].append("signin-url")
        chrome_login_and_authorize(url)
        result["steps"].append("authorized")
        time.sleep(8)
        t = app.ev("document.body.innerText") or ""
        result["app_text"] = t.replace("\n", " ")[:150]
        result["ok"] = ("Log in immediately" not in t and "Waiting" not in t)
        result["steps"].append("verify")
    except Exception as e:
        result["error"] = repr(e)
    json.dump(result, open("result.json", "w"), ensure_ascii=False, indent=1)
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0 if result["ok"] else 1)

main()