"""ちょこまな — 学習アプリのホームと共通スタンプ帳。

Architecture: Streamlit (this file) -> Supabase REST API (read-only).
Each learning app remains an independent GitHub / Streamlit application and
writes its own completed challenges to public.chokomana_stamps.

Deploy: rename this file to app.py in the hub's own GitHub repository.
Streamlit Cloud already provides streamlit; this file uses only Python stdlib
for Supabase REST requests (no supabase-py dependency).

Required Streamlit Secrets:
  SUPABASE_URL = "https://keewulninyoeylgflshb.supabase.co"
  SUPABASE_SERVICE_ROLE_KEY = "<server-side key>"  # OR SUPABASE_SECRET_KEY
  SUPABASE_PUBLISHABLE_KEY = "<optional, public key; built-in default>"

Optional Streamlit Secrets:
  KOTOBA_APP_URL = "https://...streamlit.app"
  SOROBAN_APP_URL = "https://...streamlit.app"
  GEOMETRY_APP_URL = "https://...streamlit.app"

Security: username/password accounts and sessions are verified server-side; launch tickets are one-time,
service/secret keys are kept only in the Python server process.
"""
from __future__ import annotations

import html
import json
import os
from datetime import date, datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import streamlit as st
import streamlit.components.v1 as components


TOKYO = ZoneInfo("Asia/Tokyo")
DEFAULT_SUPABASE_URL = "https://keewulninyoeylgflshb.supabase.co"
TABLE_NAME = "chokomana_stamps"
BATCH_SIZE = 400
MAX_STAMPS_PER_DAY = 10000
FIELDS = (
    "stamp_id", "profile_id", "source_app", "attempt_id", "category_key",
    "category_label", "stamp_char", "reading", "difficulty", "correct_count",
    "total_count", "grade", "finished_at", "study_date",
)
GRADE_NAMES = {"gold": "金", "silver": "銀", "bronze": "銅", "white": "白"}
SUBJECT_NAMES = {"kotoba": "国語", "soroban": "そろばん", "geometry": "図形"}
APP_DEFINITIONS = (
    {"id": "kotoba", "title": "こくご・ことば", "tag": "ことばを広げる", "symbol": "言", "secret": "KOTOBA_APP_URL", "icon": "あ"},
    {"id": "soroban", "title": "そろばん", "tag": "計算にチャレンジ", "symbol": "算", "secret": "SOROBAN_APP_URL", "icon": "123"},
    {"id": "geometry", "title": "ずけいのアトリエ", "tag": "図形で考える", "symbol": "図", "secret": "GEOMETRY_APP_URL", "icon": "△"},
)


def now_jst() -> datetime:
    return datetime.now(TOKYO)


def _setting(name: str, default: str = "") -> str:
    """Read Streamlit Secrets (or deployment environment), never render key values."""
    try:
        val = st.secrets.get(name)
    except Exception:
        val = None
    if val is None:
        val = os.environ.get(name, default)
    return str(val or "").strip()


def _valid_https_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
        return (parsed.scheme == "https" and bool(parsed.hostname)
                and parsed.username is None and parsed.password is None)
    except ValueError:
        return False


def _db_config() -> tuple[str, str, str, list[str]]:
    """Read only the profile verified from this browser's possession token."""
    profile = st.session_state.get("cm_profile", "")
    try:
        url, key = cm_service_config()
    except RuntimeError:
        return "", "", profile, ["SUPABASE_URL / SUPABASE_SECRET_KEY"]
    missing = [] if profile else ["利用者の自動連携"]
    return url, key, profile, missing


def fetch_day(url: str, public_key: str, profile_id: str, target_day: date, access_token: str = "") -> tuple[list[dict], bool]:
    """Fetch only one learner/day, with server-only authentication and paging.

    study_date is a generated JST date in PostgreSQL. No new rows are written.
    """
    if not _valid_https_url(url) or not public_key or not profile_id:
        raise ValueError("Supabase接続設定または学習者IDがありません")
    rows = []
    base = url.rstrip("/") + "/rest/v1/" + TABLE_NAME
    headers = {
        "apikey": public_key,
        "Accept": "application/json",
        "User-Agent": "chokomana-hub/2.0",
    }

    if profile_id != st.session_state.get("cm_profile"):
        raise ValueError("利用者の連携を確認できません")
    if not public_key.startswith("sb_secret_"):
        headers["Authorization"] = "Bearer " + public_key
    offset = 0
    truncated = False
    while offset < MAX_STAMPS_PER_DAY:
        page_size = min(BATCH_SIZE, MAX_STAMPS_PER_DAY - offset)
        params = urlencode({
            "select": ",".join(FIELDS),
            "profile_id": "eq." + profile_id,
            "study_date": "eq." + target_day.isoformat(),
            "order": "finished_at.asc,stamp_id.asc",
            "limit": str(page_size),
            "offset": str(offset),
        })
        req = Request(base + "?" + params, headers=headers, method="GET")
        try:
            with urlopen(req, timeout=9) as resp:
                batch = json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            # Never surface the full response body or credentials to a user.
            raise RuntimeError(f"Supabaseから取得できませんでした（HTTP {exc.code}）") from None
        except (URLError, TimeoutError, OSError) as exc:
            raise RuntimeError("Supabaseへの通信に失敗しました。接続設定をご確認ください。") from None
        except (ValueError, UnicodeError, json.JSONDecodeError):
            raise RuntimeError("Supabaseからのデータ形式を確認できませんでした。") from None
        if not isinstance(batch, list):
            raise RuntimeError("スタンプの取得形式が不正です。")
        rows.extend(x for x in batch if isinstance(x, dict))
        if len(batch) < page_size:
            break
        offset += len(batch)
    else:
        truncated = True
    return rows, truncated


def safe_int(value, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return fallback


def jst_time(iso_value) -> str:
    if not iso_value:
        return "--:--"
    try:
        source = str(iso_value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(source)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(TOKYO).strftime("%H:%M")
    except (ValueError, TypeError):
        return "--:--"


def date_label(day: date) -> str:
    weekday = "月火水木金土日"[day.weekday()]
    return f"{day.year}年{day.month}月{day.day}日（{weekday}）"


def normalize_grade(value: object) -> str:
    return str(value) if value in GRADE_NAMES else "white"


def stamp_grid_html(rows: list[dict]) -> str:
    """HTML stamp cards, HTML-escaped because Supabase columns are external data."""
    cards = []
    for row in rows:
        grade = normalize_grade(row.get("grade"))
        stamp_char = html.escape(str(row.get("stamp_char") or "学")[:1])
        reading = html.escape(str(row.get("reading") or ""))
        category = html.escape(str(row.get("category_label") or "学習"))
        subj = html.escape(SUBJECT_NAMES.get(str(row.get("source_app")), str(row.get("source_app") or "学習")))
        score = f"{safe_int(row.get('correct_count'))} / {safe_int(row.get('total_count'))}"
        when = html.escape(jst_time(row.get("finished_at")))
        cards.append(f'''
          <article class="cm-stamp-item">
            <div class="cm-stamp {grade}" aria-label="{GRADE_NAMES[grade]}スタンプ {stamp_char}">
              <span class="cm-grade">{GRADE_NAMES[grade]}</span>
              <span class="cm-stamp-char">{stamp_char}</span>
              <span class="cm-stamp-reading">{reading}</span>
            </div>
            <div class="cm-stamp-category">{category}</div>
            <div class="cm-stamp-meta">{subj} · {score}問</div>
            <div class="cm-stamp-time">{when}</div>
          </article>''')
    return re.sub(r'>\s+<', '><', '<div class="cm-stamp-grid">' + ''.join(cards) + '</div>')


def _safe_json(data: object) -> str:
    return (json.dumps(data, ensure_ascii=False)
            .replace("<", "\\u003c").replace(">", "\\u003e")
            .replace("&", "\\u0026")
            .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def voice_panel(rows: list[dict]) -> str:
    """Single continuous Japanese TTS utterance with ascending 2-octave melody.

    No per-syllable speechSynthesis.speak: that introduced audible gaps.
    Playback requires an explicit browser gesture (Play button).
    """
    payload = [{
        "char": str(row.get("stamp_char") or "学")[:1],
        "reading": str(row.get("reading") or "")[:24],
        "grade": normalize_grade(row.get("grade")),
    } for row in rows]
    template = r'''<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<style>
*{box-sizing:border-box}body{margin:0;background:transparent;color:#26364a;font-family:system-ui,"Noto Sans JP",sans-serif}
.panel{padding:8px 1px 3px}.tiles{display:flex;gap:8px;overflow-x:auto;scrollbar-width:thin;padding:9px 5px 13px}
.tile{flex:0 0 53px;width:53px;height:53px;border-radius:50%;border:3px double #bbb;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:0;box-shadow:inset 0 3px 8px #fff8,0 4px 8px #0001;transition:transform .1s ease,box-shadow .1s ease}
.tile b{font-size:23px;line-height:1.1}.tile small{font-size:10px;font-weight:bold}.tile.gold{background:radial-gradient(circle at 27% 16%,#fff9dc,#f3c744 60%,#ba7a14);color:#704d0c;border-color:#c38e22}
.tile.silver{background:radial-gradient(circle at 27% 16%,white,#d5dce5 60%,#8b9cac);color:#41566b;border-color:#99a6b4}
.tile.bronze{background:radial-gradient(circle at 27% 16%,#fff1dd,#ce8d5d 60%,#92532c);color:#693c23;border-color:#aa6e43}
.tile.white{background:radial-gradient(circle at 27% 16%,white,#f5f6f7 60%,#d0d8de);color:#495667;border-color:#b4bec9}
.tile.active{transform:translateY(-6px) scale(1.12);box-shadow:0 5px 0 #7ab9a1,inset 0 4px 9px #fff7}
.controls{display:flex;gap:9px}.controls button{border:0;border-radius:13px;padding:13px 11px;font-weight:800;font-size:14px;cursor:pointer}
#play{flex:1;background:#287466;color:white}#stop{background:#ffffff;color:#245a4b;border:1px solid #9bb6a8;min-width:78px}
#status{text-align:center;color:#66758a;font-size:12px;min-height:23px;padding:8px 0}

</style></head><body><div class="panel">
<div class="tiles" id="tiles" aria-label="スタンプの読み上げ順"></div>
<div class="controls"><button id="play" type="button">▶ スタンプを読み上げる</button><button id="stop" type="button">停止</button></div>
<div id="status" role="status">日本語の声と上昇メロディーで読み上げます</div>
</div><script>
(()=>{
const items=__STAMPS__, tiles=document.getElementById('tiles'),status=document.getElementById('status');
const AC=window.AudioContext||window.webkitAudioContext;
let ctx=null,raf=0,token=0,voice=null;
items.forEach(x=>{const e=document.createElement('span');e.className='tile '+x.grade;const b=document.createElement('b');b.textContent=x.char;const sm=document.createElement('small');sm.textContent=x.reading;e.append(b,sm);tiles.appendChild(e)});
const boxes=[...tiles.children];
function mark(i){boxes.forEach((e,j)=>e.classList.toggle('active',j===i));if(i>=0&&boxes[i])boxes[i].scrollIntoView({block:'nearest',inline:'nearest',behavior:'smooth'})}
function stop(message='停止しました'){
 token++;if(raf)cancelAnimationFrame(raf);raf=0;
 if(ctx){const old=ctx;ctx=null;old.close().catch(()=>{})}
 if('speechSynthesis' in window)window.speechSynthesis.cancel();voice=null;mark(-1);status.textContent=message;
}
function note(ac,t,hz,previous,d,out){
 const env=ac.createGain();env.gain.setValueAtTime(.0001,t);env.gain.exponentialRampToValueAtTime(.16,t+.027);env.gain.setValueAtTime(.16,t+d-.055);env.gain.exponentialRampToValueAtTime(.0001,t+d+.025);env.connect(out);
 const o=ac.createOscillator();o.type='sawtooth';o.frequency.setValueAtTime(previous||hz*.94,t);o.frequency.exponentialRampToValueAtTime(hz,t+.085);
 const filter=ac.createBiquadFilter();filter.type='lowpass';filter.frequency.value=1030;const gain=ac.createGain();gain.gain.value=.20;o.connect(filter).connect(gain).connect(env);o.start(t);o.stop(t+d+.027);
 const sine=ac.createOscillator();sine.type='sine';sine.frequency.setValueAtTime(previous||hz*.94,t);sine.frequency.exponentialRampToValueAtTime(hz,t+.085);const sg=ac.createGain();sg.gain.value=.14;sine.connect(sg).connect(env);sine.start(t);sine.stop(t+d+.027);
}
const play=document.getElementById('play');
play.addEventListener('click',async()=>{
 if(!items.length){status.textContent='スタンプがありません';return}
 stop('読み上げ中…');const id=token;
 // One continuous Japanese utterance, not one utterance per stamp.
 if('speechSynthesis' in window&&'SpeechSynthesisUtterance' in window){
  const synth=window.speechSynthesis;const u=new SpeechSynthesisUtterance(items.map(x=>x.reading).join(''));
  u.lang='ja-JP';u.rate=2.15;u.pitch=1.5;u.volume=1;
  const ja=synth.getVoices().find(v=>v.lang&&v.lang.toLowerCase()==='ja-jp')||synth.getVoices().find(v=>v.lang&&v.lang.toLowerCase().startsWith('ja'));
  if(ja)u.voice=ja;voice=u;u.onerror=e=>{if(id===token&&!['canceled','interrupted'].includes(e.error))status.textContent='日本語音声はこの端末で利用できません'};
  synth.speak(u);
 }else{status.textContent='日本語音声はこの端末で利用できません'}
 if(!AC)return;
 const ac=new AC();ctx=ac;try{await ac.resume()}catch(e){if(id===token)status.textContent='メロディーを再生できません';return}
 if(token!==id)return;
 const compressor=ac.createDynamicsCompressor();compressor.threshold.value=-22;compressor.ratio.value=3;compressor.connect(ac.destination);
 const bus=ac.createGain();bus.gain.value=.60;bus.connect(compressor);
 const delay=ac.createDelay(.25);delay.delayTime.value=.079;const wet=ac.createGain();wet.gain.value=.10;bus.connect(delay);delay.connect(wet).connect(compressor);
 const n=items.length,step=n>25?.17:n>12?.19:.23,starts=[];let t=ac.currentTime+.05;
 items.forEach((x,i)=>{const f=196*Math.pow(4,i/Math.max(1,n-1));const previous=i?196*Math.pow(4,(i-1)/Math.max(1,n-1))*.94:null;starts.push(t);note(ac,t,f,previous,step+.08,bus);t+=step});
 const finished=t+.18;
 function tick(){if(token!==id||ctx!==ac)return;const now=ac.currentTime;let i=-1;for(let k=0;k<starts.length;k++)if(now>=starts[k])i=k;mark(i);
 if(i>=0)status.textContent=(i+1)+' / '+n+'　'+items[i].reading+'！';
 if(now<finished){raf=requestAnimationFrame(tick)}else{mark(-1);status.textContent=n+'個のスタンプを確認しました';raf=0}}
 raf=requestAnimationFrame(tick);
});
document.getElementById('stop').addEventListener('click',()=>stop());
})();
</script></body></html>'''
    return template.replace("__STAMPS__", _safe_json(payload))


STYLES = """
<style>
:root { --cm-ink:#24344e; --cm-muted:#68778a; --cm-outline:#e0e7ee; }
.stApp {background:linear-gradient(175deg,#f8fafc 0%,#f5f8fa 58%,#f9f8f4 100%); color:var(--cm-ink)}
.block-container{max-width:1030px;padding-top:1.2rem;padding-bottom:4rem}
#MainMenu,footer{visibility:hidden}
h1,h2,h3{color:#263a56 !important}
.cm-brand{display:flex;align-items:center;gap:14px;margin:0 0 7px}
.cm-logo{display:grid;place-items:center;width:52px;height:52px;border-radius:17px;background:#305fa7;color:#fff;font-weight:900;font-size:27px;box-shadow:0 8px 18px #325fa52a}
.cm-brand h1{margin:0;font-size:clamp(25px,4.4vw,34px);font-weight:900;letter-spacing:.02em}
.cm-brand p{margin:0;color:var(--cm-muted);font-size:13px}
.cm-hero{border-radius:22px;padding:25px 24px;background:linear-gradient(115deg,#315d9c,#477eba);color:white;margin:18px 0 17px;box-shadow:0 9px 23px #254a8030}
.cm-hero h2{color:white!important;font-size:clamp(20px,4.8vw,28px);font-weight:850;margin:0 0 6px}
.cm-hero p{color:#edf4ff;margin:0;font-size:14px}
.cm-app-art{border-radius:15px;min-height:117px;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:7px;background:linear-gradient(145deg,#f4f8ff,#e6eff9);margin-bottom:8px}
.cm-app-art .icon{font-size:36px;font-weight:900;color:#315d95;line-height:1.1}
.cm-app-art .name{font-size:17px;font-weight:850;color:#27466c}
.cm-app-art .tag{font-size:12px;color:#677c92}
.cm-page-heading{font-size:23px;font-weight:860;color:#253d5c;margin:21px 0 5px}
.cm-note{font-size:13px;color:var(--cm-muted);margin:1px 0 11px}
.cm-stamp-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(128px,1fr));gap:19px 9px;padding:15px 5px 19px}
.cm-stamp-item{text-align:center;min-width:0}
.cm-stamp{width:101px;height:101px;border-radius:50%;border:5px double #b6bfc6;box-shadow:inset 0 6px 13px #ffffffa1,inset 0 -8px 14px #00000011,0 6px 14px #101f2b20;display:flex;align-items:center;justify-content:center;flex-direction:column;margin:0 auto 8px}
.cm-stamp.gold{background:radial-gradient(circle at 28% 18%,#fff9cf,#f5d361 49%,#c38d1d);border-color:#bd8c26;color:#69470a}
.cm-stamp.silver{background:radial-gradient(circle at 28% 18%,#fff,#d8e0e8 53%,#9aa8b8);border-color:#9aa9b8;color:#3d5266}
.cm-stamp.bronze{background:radial-gradient(circle at 28% 18%,#fff1dd,#d99c6e 53%,#a6653d);border-color:#ad7044;color:#60391e}
.cm-stamp.white{background:radial-gradient(circle at 28% 18%,#fff,#f8f9fb 54%,#d7dde2);border-color:#b9c2cb;color:#4c5b6a}
.cm-grade{font-size:11px;line-height:1.1;font-weight:850}
.cm-stamp-char{font-size:37px;font-weight:900;line-height:1.2}
.cm-stamp-reading{font-size:12px;font-weight:850;line-height:1.1}
.cm-stamp-category{font-size:13px;font-weight:800;color:#2c425e;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cm-stamp-meta,.cm-stamp-time{font-size:11px;color:#66778c}
.cm-empty{border:1px dashed #c6d3e2;background:#ffffffb8;border-radius:18px;text-align:center;padding:26px 13px;color:#5e7187;margin:20px 0}
.cm-game-title{display:flex;align-items:center;gap:11px}
.cm-pill{background:#eef4fc;color:#315887;border-radius:50px;font-size:12px;font-weight:800;padding:6px 12px}
[data-testid="stVerticalBlockBorderWrapper"]{border-color:var(--cm-outline)}
@media(max-width:640px){.cm-stamp-grid{grid-template-columns:repeat(auto-fill,minmax(99px,1fr));gap:15px 5px}.cm-stamp{width:86px;height:86px}.cm-stamp-char{font-size:31px}.cm-hero{padding:21px 17px}}

/* Home refresh: scoped cards retain native Streamlit controls and links. */
:root{--cm-ink:#233c3c;--cm-muted:#657875;--cm-outline:#e3e9e4}
.stApp{background:#fafbf7;color:var(--cm-ink)}
.block-container{max-width:1060px;padding-top:2.4rem}
h1,h2,h3{color:#233c3c!important}
.cm-brand{gap:12px;margin-bottom:18px}
.cm-logo{width:46px;height:46px;border-radius:16px;background:#287466;box-shadow:none;font-size:25px}
.cm-brand h1{font-size:29px;letter-spacing:.06em;color:#233c3c!important;padding:0;line-height:1.4}
.cm-brand p{font-size:12px;margin-top:4px}
[class*="st-key-nav_"] button{border:0!important;background:transparent!important;color:#687975!important;border-radius:12px!important;box-shadow:none!important;min-height:44px}
[class*="st-key-nav_"] button[kind="primary"]{background:#e5efe8!important;color:#225b4e!important}
[class*="st-key-nav_"] button p{font-weight:700}
.cm-hero{position:relative;overflow:hidden;background:#eef4e9;border:1px solid #e1ebdd;border-radius:26px;color:#233c3c;box-shadow:none;padding:30px 32px;margin:20px 0 8px}
.cm-hero h2{font-size:clamp(24px,4.5vw,34px);color:#233c3c!important;letter-spacing:.04em;line-height:1.5;margin:3px 0 7px}
.cm-hero p{color:#5c7368;font-size:14px;line-height:1.8}
.cm-eyebrow{color:#4c7a63;font-size:11px;font-weight:750;letter-spacing:.14em}
.cm-hero-copy{position:relative;z-index:1;padding-right:140px}
.cm-hero-art{position:absolute;right:34px;top:24px;width:126px;height:126px;transform:rotate(-8deg);color:#326653}
.cm-page-heading{color:#233c3c;font-size:20px;margin:22px 0 8px;font-weight:800}
.cm-section-hint{font-size:12px;font-weight:400;color:#71817a;margin-left:12px}
[class*="st-key-subject_"]{--subject:#287466;--wash:#e9f1e9}
.st-key-subject_kotoba{--subject:#b14f43;--wash:#f9ece6}
.st-key-subject_soroban{--subject:#326dac;--wash:#eaf1fa}
.st-key-subject_geometry{--subject:#826221;--wash:#f7f0db}
[class*="st-key-subject_"]{background:white;border:1px solid #e3e8df!important;border-radius:22px!important;padding:20px!important;box-shadow:0 5px 16px #233c3c05}
.cm-app-art{min-height:182px;margin:0 0 14px;background:transparent;gap:9px}
.cm-app-art .icon{display:grid;place-items:center;width:84px;height:84px;border-radius:27px;background:var(--wash);color:var(--subject);font-size:36px;margin-bottom:10px;transform:rotate(-5deg)}
.cm-app-art .icon span{transform:rotate(5deg)}
.cm-app-art .name{color:#293f3a;font-size:19px}
.cm-app-art .tag{color:#718078;font-size:12px}
[class*="st-key-subject_"] [data-testid="stLinkButton"] a{background:var(--wash)!important;color:var(--subject)!important;border:1px solid transparent!important;border-radius:12px;min-height:46px;box-shadow:none;font-weight:750}
[class*="st-key-subject_"] [data-testid="stLinkButton"] a:hover{border-color:var(--subject)!important;filter:brightness(.98)}
[class*="st-key-subject_"] [data-testid="stLinkButton"] a:focus-visible{outline:3px solid var(--subject);outline-offset:3px}
.st-key-home_progress{background:#fff;border:1px solid #e3e8df!important;border-radius:20px!important;padding:20px 24px!important;margin-top:14px}
.cm-progress-heading{font-size:19px;font-weight:800;color:#233c3c;margin-bottom:6px}
.cm-progress-heading span{color:#b58c32;margin-right:8px}
.st-key-home_today button{background:#287466!important;border-color:#287466!important;color:white!important;border-radius:12px;min-height:46px}
.cm-note{color:#6b7b73;line-height:1.7}
@media(max-width:640px){
.block-container{padding:1.5rem 1rem 3rem}
.cm-brand h1{font-size:25px}
.cm-brand p{font-size:10px}
.cm-hero{padding:23px 20px;border-radius:22px}
.cm-hero-copy{padding-right:0}
.cm-hero-art{display:none}
.cm-hero h2{font-size:25px}
.cm-hero p{font-size:12px}
.cm-section-hint{display:block;margin:5px 0 0}
[class*="st-key-subject_"]{padding:16px!important}
.cm-app-art{min-height:150px}
.st-key-home_progress{padding:18px!important}
[class*="st-key-nav_"] button p{font-size:12px}
}

/* Compact, child-friendly home. Scope column overrides to navigation only. */
header[data-testid="stHeader"]{display:none!important}
.block-container{padding-top:1.2rem!important;padding-bottom:2rem!important}
.cm-brand{margin:0;gap:10px;padding-bottom:16px}
.cm-brand h1{font-size:27px!important;line-height:1.35!important;padding:0!important}
.cm-brand p{font-size:11px;line-height:1.7;margin-top:5px}
.cm-logo{width:42px;height:42px;flex:0 0 42px;border-radius:14px;font-size:25px}
.st-key-cm_navigation [data-testid="stHorizontalBlock"]{flex-wrap:nowrap!important;gap:8px!important}
.st-key-cm_navigation [data-testid="stColumn"]{min-width:0!important;width:calc((100% - 16px)/3)!important;flex:1 1 0!important}
[class*="st-key-nav_"] button{min-height:44px!important;padding:6px 4px!important}
[class*="st-key-nav_"] button p{font-size:13px!important;white-space:nowrap}
.cm-home-question{font-size:23px!important;font-weight:800;line-height:1.4!important;padding:0 0 18px!important;margin:8px 0 0!important}
.cm-subject-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;padding-bottom:24px}
.cm-subject{--subject:#b14f43;--wash:#fff0e9;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;padding:23px 10px 16px;border:2px solid #efcabc;border-radius:22px;background:var(--wash);color:var(--subject)!important;text-decoration:none!important;min-width:0;box-shadow:0 4px 0 #efcabc;transition:transform .12s}
.cm-subject-soroban{--subject:#28689b;--wash:#edf5ff;border-color:#c0d7ee;box-shadow:0 4px 0 #c0d7ee}
.cm-subject-geometry{--subject:#886319;--wash:#fff7dd;border-color:#e8d89f;box-shadow:0 4px 0 #e8d89f}
.cm-subject-icon{display:block;width:68px;height:68px;flex-shrink:0}
.cm-subject-icon svg{display:block;width:100%;height:100%}
.cm-subject-label{font-size:24px;font-weight:850;line-height:1.4;white-space:nowrap}
.cm-subject-go{display:flex;align-items:center;flex-wrap:nowrap;white-space:nowrap;gap:4px;font-size:14px;font-weight:750;line-height:1.6;letter-spacing:.03em;background:#ffffffb8;border-radius:50px;padding:6px 16px}
a.cm-subject:hover{transform:translateY(-2px);text-decoration:none!important}
a.cm-subject:active{transform:translateY(2px);box-shadow:none}
a.cm-subject:focus-visible{outline:3px solid #287466;outline-offset:4px}
.cm-subject-disabled{opacity:.55}
.st-key-home_progress{padding:16px!important;margin-top:0}
.cm-progress-heading{font-size:17px;margin-bottom:3px}
@media(max-width:640px){
.block-container{padding:16px 14px 36px!important}
[data-testid="stMainBlockContainer"]>[data-testid="stVerticalBlock"]{gap:12px!important}
.cm-brand h1{font-size:24px!important}
.cm-brand p{font-size:10px}
.cm-brand{margin-bottom:0;padding-bottom:16px}
.cm-home-question{font-size:21px!important;margin:8px 0 0!important;padding-bottom:18px!important}
.cm-subject-grid{gap:9px;padding-bottom:24px}
.cm-subject{border-radius:17px;padding:15px 4px 11px;gap:10px}
.cm-subject-icon{width:48px;height:48px}
.cm-subject-label{font-size:18px}
.cm-subject-go{font-size:12px;padding:5px 9px}
.st-key-home_progress{padding:14px!important;margin-top:0}
[class*="st-key-nav_"] button p{font-size:11px!important}
.st-key-cm_navigation [data-testid="stHorizontalBlock"]{gap:4px!important}
.st-key-cm_navigation [data-testid="stColumn"]{width:calc((100% - 8px)/3)!important}
}
@media(max-width:350px){.cm-subject-label{font-size:16px}.cm-subject-icon{width:42px;height:42px}.cm-brand p{font-size:9px}}

.cm-signin-title{font-size:23px;font-weight:800;line-height:1.6;color:#233c3c;margin:12px 0 8px}
.cm-signin-note{font-size:14px;line-height:1.9;color:#61756e;margin:0 0 16px}
.st-key-cm_account_form{max-width:520px;background:white;border-radius:20px!important;padding:20px!important}
.st-key-cm_account_form label{font-weight:700}
.st-key-cm_account_form [data-testid="stVerticalBlock"]{gap:12px}
.st-key-cm_account_form [data-testid="stFormSubmitButton"] button{min-height:48px;background:#287466!important;border-color:#287466!important;color:white;border-radius:12px}
.st-key-cm_account_mode [role="radiogroup"]{gap:12px}
.st-key-cm_account_mode [data-testid="stMarkdownContainer"] p{font-size:15px}
@media(max-width:640px){.cm-signin-title{font-size:21px}.st-key-cm_account_form{padding:16px!important}.cm-signin-note{font-size:13px}}
/* Native Streamlit widgets must match the app's light surface in either OS theme. */
.stApp{color-scheme:light;--st-text-color:#233c3c;--st-background-color:#fafbf7;--st-secondary-background-color:#f5f8f6;--st-primary-color:#287466;--st-border-color:#bacbc1}
.stApp [data-testid="stWidgetLabel"],
.stApp [data-testid="stWidgetLabel"] p,
.stApp [data-testid="stWidgetLabel"] span,
.stApp [data-testid="stRadioOption"],
.stApp [data-testid="stRadioOption"] p,
.stApp [data-testid="stRadioOption"] span{color:#233c3c!important;-webkit-text-fill-color:#233c3c!important}
.st-key-cm_account_form [data-testid="stMarkdownContainer"],
.st-key-cm_account_form [data-testid="stMarkdownContainer"] p,
.st-key-cm_account_form [data-testid="stMarkdownContainer"] strong{color:#233c3c!important}
.stApp [data-testid="stTextInputRootElement"],
.stApp [data-testid="stTextInput"] [data-baseweb="input"]{background:#ffffff!important;color:#233c3c!important;border:1px solid #bacbc1!important;border-radius:10px!important;color-scheme:light}
.stApp [data-testid="stTextInput"] input{background:transparent!important;color:#233c3c!important;-webkit-text-fill-color:#233c3c!important;caret-color:#233c3c!important;border:none!important}
.stApp [data-testid="stTextInput"] input::placeholder{color:#65796e!important;-webkit-text-fill-color:#65796e!important;opacity:1!important}
.stApp [data-testid="stTextInputRootElement"]:focus-within{outline:2px solid #287466;outline-offset:2px}
.stApp [data-testid="stTextInputRootElement"] button,
.stApp [data-testid="stTextInputRootElement"] button span,
.stApp [data-testid="stTextInputRootElement"] button svg{color:#425f52!important;-webkit-text-fill-color:#425f52!important;background:transparent!important}
.stApp [data-testid="stTooltipIcon"],
.stApp [data-testid="stTooltipIcon"] svg{color:#425f52!important}
.stApp input:-webkit-autofill{-webkit-text-fill-color:#233c3c!important;box-shadow:0 0 0 1000px #ffffff inset!important}
.st-key-cm_account_form [data-testid="stFormSubmitButton"] button,
.st-key-cm_account_form [data-testid="stFormSubmitButton"] button p,
.st-key-cm_account_form [data-testid="stFormSubmitButton"] button span{color:#ffffff!important;-webkit-text-fill-color:#ffffff!important}
.stApp [data-testid="stCaptionContainer"],
.stApp [data-testid="stCaptionContainer"] p{color:#61756e!important;-webkit-text-fill-color:#61756e!important}
.st-key-cm_account_form [data-testid="stAlert"]{background:#fff0ec!important;color:#842c20!important;border-color:#e6b6ac!important}
.st-key-cm_account_form [data-testid="stAlert"] [data-testid="stMarkdownContainer"],
.st-key-cm_account_form [data-testid="stAlert"] [data-testid="stMarkdownContainer"] p{color:#842c20!important;-webkit-text-fill-color:#842c20!important}
[class*="st-key-nav_"] button p{color:inherit!important;-webkit-text-fill-color:currentColor!important}

.st-key-cm_account_mode [role="radiogroup"]{display:flex;flex-wrap:wrap;gap:12px!important}
.st-key-cm_account_mode [data-testid="stRadioOption"]{white-space:nowrap!important;flex-shrink:0;min-height:44px;padding:8px 10px;border:1px solid #bacbc1;border-radius:12px;background:#ffffff}
.st-key-cm_account_mode [data-testid="stRadioOption"] p{white-space:nowrap!important;word-break:keep-all}
.st-key-cm_account_mode [data-testid="stRadioOption"]:has(input:checked){background:#e5efe8;border-color:#287466}

/* Shared control palette: all pages use the same light surfaces and green actions. */
.stApp [data-testid="stButton"] button,
.stApp [data-testid="stFormSubmitButton"] button{background:#ffffff!important;border:1px solid #9bb6a8!important;color:#245a4b!important;border-radius:12px;min-height:44px}
.stApp [data-testid="stButton"] button p,.stApp [data-testid="stButton"] button span,
.stApp [data-testid="stFormSubmitButton"] button p{color:inherit!important;-webkit-text-fill-color:currentColor!important}
.stApp [data-testid="stButton"] button:hover:not(:disabled){background:#e5efe8!important;border-color:#287466!important}
.stApp [data-testid="stButton"] button[kind="primary"],
.stApp [data-testid="stFormSubmitButton"] button[kind="primary"]{background:#287466!important;color:#ffffff!important;border-color:#287466!important}
.stApp [data-testid="stButton"] button:disabled,
.stApp [data-testid="stFormSubmitButton"] button:disabled{background:#edf1ee!important;color:#61756e!important;border-color:#cedbd3!important;opacity:1}
.stApp [class*="st-key-nav_"] button{background:transparent!important;color:#526b60!important;border-color:transparent!important}
.stApp [class*="st-key-nav_"] button[kind="primary"]{background:#e5efe8!important;color:#225b4e!important;border-color:transparent!important}
.stApp [data-testid="stDateInput"] [data-baseweb="input"],
.stApp [data-testid="stDateInput"] [data-baseweb="base-input"]{background:#ffffff!important;color:#233c3c!important;border-color:#bacbc1!important;color-scheme:light}
.stApp [data-testid="stDateInput"] input{background:#ffffff!important;color:#233c3c!important;-webkit-text-fill-color:#233c3c!important;caret-color:#233c3c!important}
.stApp [data-testid="stDateInput"] svg,.stApp [data-testid="stDateInput"] button{color:#425f52!important}
[data-baseweb="calendar"],[data-baseweb="calendar"] [role="grid"],
[data-baseweb="calendar"] [role="row"],[data-baseweb="calendar"] [role="gridcell"],
[data-baseweb="calendar"] button{background:#ffffff!important;color:#233c3c!important}
[data-baseweb="calendar"] [aria-selected="true"],[data-baseweb="calendar"] [aria-selected="true"] button{background:#287466!important;color:#ffffff!important}
[data-baseweb="calendar"] button:disabled,[data-baseweb="calendar"] [aria-disabled="true"]{color:#83988b!important}
[data-baseweb="calendar"] [data-baseweb="select"],[data-baseweb="calendar"] [data-baseweb="select"] div{background:#ffffff!important;color:#233c3c!important}
[data-baseweb="popover"] [role="listbox"],[data-baseweb="popover"] [role="option"]{background:#ffffff!important;color:#233c3c!important}
[data-baseweb="popover"] [role="option"][aria-selected="true"]{background:#e5efe8!important;color:#225b4e!important}
.stApp [data-testid="stExpander"] details{background:#ffffff!important;color:#233c3c!important;border-color:#d6e1da!important}
.stApp [data-testid="stExpander"] summary,.stApp [data-testid="stExpander"] summary p,
.stApp [data-testid="stExpander"] summary span{color:#233c3c!important;-webkit-text-fill-color:#233c3c!important}
.stApp [data-testid="stMarkdownContainer"]>p{color:#233c3c}
.stApp [data-testid="stAlert"]{background:#edf5f3;color:#245a4b}
.stApp [data-testid="stAlert"] [data-testid="stMarkdownContainer"] p{color:#245a4b!important;-webkit-text-fill-color:#245a4b!important}
.cm-stamp-totals{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px;margin:4px 0 12px}
.cm-total{display:flex;flex-direction:column;align-items:center;gap:3px;padding:9px 3px;background:#ffffff;border:1px solid #d6e1da;border-radius:12px;color:#233c3c}
.cm-total span{font-size:12px;line-height:1.4;color:#526b60}
.cm-total strong{font-size:22px;line-height:1.4;color:#233c3c}
.cm-stamp-grid{grid-template-columns:repeat(5,minmax(0,1fr));grid-auto-flow:row;align-content:start;align-items:start;justify-items:start;height:auto;min-height:0;grid-auto-rows:auto;margin:0;padding:8px 0 18px}
.cm-stamp-item{width:100%;margin:0;align-self:start}
@media(max-width:640px){.cm-stamp-totals{gap:5px;margin-bottom:8px}.cm-total{padding:7px 2px}.cm-total strong{font-size:19px}.cm-stamp-grid{grid-template-columns:repeat(3,minmax(0,1fr));gap:18px 8px}.cm-stamp-category{font-size:12px;white-space:normal;line-height:1.5}.cm-stamp-meta{font-size:10px;line-height:1.5}}

[data-baseweb="calendar"] span,[data-baseweb="calendar"] div{color:#233c3c!important;-webkit-text-fill-color:#233c3c!important}
[data-baseweb="calendar"] [aria-selected="true"],[data-baseweb="calendar"] [aria-selected="true"] *{color:#ffffff!important;-webkit-text-fill-color:#ffffff!important}
[data-baseweb="popover"] [role="option"] *{color:#233c3c!important;-webkit-text-fill-color:#233c3c!important}
.stApp [data-testid="stAlert"] [data-testid="stAlertContainer"]{background:#edf5f3!important}
.stApp .st-key-cm_account_form [data-testid="stAlert"] [data-testid="stMarkdownContainer"],
.stApp .st-key-cm_account_form [data-testid="stAlert"] [data-testid="stMarkdownContainer"] p{color:#842c20!important;-webkit-text-fill-color:#842c20!important}
/* Daily assignments share the existing account colors, with clear row spacing. */
.cm-plan-list{list-style:none;margin:16px 0;padding:0;display:grid;gap:14px}
.cm-plan-item{display:grid;grid-template-columns:30px minmax(0,1fr);gap:10px;align-items:start;padding:14px 12px;border:1px solid #d6e1da;border-radius:14px;background:#ffffff;color:#233c3c}
.cm-plan-number{display:block;align-self:start;width:28px;height:28px;line-height:28px;border-radius:50%;background:#e5efe8;color:#225b4e;text-align:center;font-weight:800}
.cm-plan-item h3{font-size:16px!important;line-height:1.6!important;margin:4px 0 8px!important;padding:0!important;overflow-wrap:anywhere;color:#233c3c!important}
.cm-plan-item p{font-size:13px;line-height:1.7;margin:4px 0;color:#526b60;overflow-wrap:anywhere}
.cm-plan-subject{font-size:12px;color:#526b60;line-height:1.6}
.cm-plan-path{padding-top:6px;border-top:1px solid #edf1ee}
.st-key-cm_daily_plan{margin:16px 0 20px!important}
.stApp [data-testid="stNumberInput"] input,.stApp [data-testid="stNumberInput"] [data-baseweb="input"],
.stApp [data-testid="stNumberInput"] [data-baseweb="base-input"]{background:#ffffff!important;color:#233c3c!important;-webkit-text-fill-color:#233c3c!important;color-scheme:light}
.stApp [data-testid="stNumberInput"] button{background:#edf5f3!important;color:#245a4b!important}
.stApp [data-testid="stLinkButton"] a{background:#287466!important;border:1px solid #287466!important;border-radius:12px;min-height:44px;color:#ffffff!important}
.stApp [data-testid="stLinkButton"] a p{color:#ffffff!important;-webkit-text-fill-color:#ffffff!important}
</style>
"""


def render_header() -> None:
    st.markdown('''<div class="cm-brand"><div class="cm-logo">ち</div>
      <div><h1>ちょこまな</h1><p>あそんで、まなんで、スタンプをあつめよう</p></div></div>''',
      unsafe_allow_html=True)


def render_navigation() -> None:
    with st.container(key="cm_navigation"):
        cols = st.columns(3, gap="small")
    labels = (("home", "ホーム"), ("today", "今日の成果"), ("history", "過去のスタンプ"))
    for col, (page, label) in zip(cols, labels):
        with col:
            if st.button(label, key="nav_" + page, use_container_width=True,
                         type="primary" if st.session_state.cm_page == page else "secondary"):
                if page == "today":
                    _open_today()
                else:
                    st.session_state.cm_page = page
                st.rerun()


def _open_today() -> None:
    st.session_state.cm_page = "today"
    st.session_state.cm_today_requested = True
    st.session_state.cm_today_rows = None
    st.session_state.cm_today_error = None


def _load_today_if_requested(url: str, key: str, profile: str, missing: list[str]) -> None:
    if not st.session_state.get("cm_today_requested"):
        return
    day = now_jst().date()
    if st.session_state.get("cm_today_loaded_for") == day:
        return
    st.session_state.cm_today_loaded_for = day
    if missing:
        st.session_state.cm_today_error = "Supabase接続設定が不足しています。"
        st.session_state.cm_today_rows = None
        return
    try:
        rows, truncated = fetch_day(url, key, profile, day, st.session_state.get("cm_access_token", ""))
        st.session_state.cm_today_rows = rows
        st.session_state.cm_today_truncated = truncated
        st.session_state.cm_today_error = None
    except RuntimeError as exc:
        st.session_state.cm_today_error = str(exc)
        st.session_state.cm_today_rows = None


def _make_launch_link(app: dict) -> str:
    """Issue the single-use code consumed by the independently hosted child app."""
    from datetime import datetime, timedelta, timezone
    if not _valid_https_url(app["url"]):
        raise ValueError("HTTPSの学習アプリURLを設定してください")
    profile = st.session_state.get("cm_profile")
    if not profile:
        raise RuntimeError("利用者の連携を準備しています")
    now = datetime.now(timezone.utc)
    cache_key = "cm_link_" + app["id"]
    cached = st.session_state.get(cache_key)
    if cached and cached.get("profile") == profile and cached.get("url") == app["url"]:
        if cached["expiry"] > now + timedelta(seconds=70):
            return cached["link"]
    code = cm_issue_ticket(profile, app["id"])
    link = cm_launch_url(app["url"], code)
    st.session_state[cache_key] = {
        "profile": profile, "url": app["url"], "link": link,
        "expiry": now + timedelta(seconds=CM_TICKET_SECONDS),
    }
    return link


def home_cards_html(apps: list[dict]) -> str:
    """One native anchor per subject, kept side-by-side at phone widths."""
    labels = {"kotoba": "こくご", "soroban": "そろばん", "geometry": "ずけい"}
    icons = {
        "kotoba": '<svg viewBox="0 0 64 64" aria-hidden="true"><path d="M8 13c10-3 17-1 24 4 7-5 14-7 24-4v37c-9-3-16-1-24 4-8-5-15-7-24-4Z" fill="currentColor" opacity=".16"/><path d="M8 13c10-3 17-1 24 4 7-5 14-7 24-4v37c-9-3-16-1-24 4-8-5-15-7-24-4Zm24 4v37M15 25l10 3m-10 7 10 3m14-10 10-3m-10 13 10-3" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>',
        "soroban": '<svg viewBox="0 0 64 64" aria-hidden="true"><rect x="6" y="10" width="52" height="44" rx="5" fill="currentColor" opacity=".12"/><g fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"><path d="M6 10h52v44H6ZM7 28h50M19 14v36m13-36v36m13-36v36"/></g><g fill="currentColor"><path d="m12 21 7-5 7 5-7 5Zm13 0 7-5 7 5-7 5Zm13 0 7-5 7 5-7 5ZM12 35l7-5 7 5-7 5Zm0 11 7-5 7 5-7 5Zm13-11 7-5 7 5-7 5Zm0 11 7-5 7 5-7 5Zm13-11 7-5 7 5-7 5Zm0 11 7-5 7 5-7 5Z"/></g></svg>',
        "geometry": '<svg viewBox="0 0 64 64" aria-hidden="true"><circle cx="21" cy="23" r="14" fill="currentColor" opacity=".18"/><circle cx="21" cy="23" r="14" stroke="currentColor" stroke-width="3" fill="none"/><path d="m38 14 20 34H18Z" fill="currentColor" opacity=".3"/><path d="m38 14 20 34H18Z" fill="none" stroke="currentColor" stroke-width="3" stroke-linejoin="round"/><path d="M8 40h19v17H8Z" fill="currentColor" opacity=".65"/></svg>',
    }
    cards = []
    for app in apps:
        app_id = app["id"]
        label = labels.get(app_id, app["title"])
        icon_color = {"kotoba": "#b14f43", "soroban": "#28689b", "geometry": "#886319"}.get(app_id, "#287466")
        icon = icons.get(app_id, "").replace("currentColor", icon_color)
        body = (f'<span class="cm-subject-icon">{icon}</span>'
                f'<span class="cm-subject-label">{html.escape(label)}</span>')
        if app["ready"]:
            try:
                link = _make_launch_link(app)
                cards.append(f'<a class="cm-subject cm-subject-{html.escape(app_id)}" '
                             f'href="{html.escape(link, quote=True)}" target="_blank" rel="noopener noreferrer" '
                             f'aria-label="{html.escape(app["title"], quote=True)}を別タブで開く">'
                             f'{body}<span class="cm-subject-go">あそぶ<span aria-hidden="true"> →</span></span></a>')
                continue
            except (RuntimeError, ValueError):
                pass
        cards.append(f'<div class="cm-subject cm-subject-{html.escape(app_id)} cm-subject-disabled" '
                     f'aria-disabled="true">{body}<span class="cm-subject-go">じゅんび中</span></div>')
    return '<div class="cm-subject-grid">' + "".join(cards) + '</div>'


def render_home(apps: list[dict]) -> None:
    st.markdown('<h2 class="cm-home-question">なにを まなぶ？</h2>', unsafe_allow_html=True)
    @st.fragment(run_every=60)
    def launch_cards():
        st.markdown(home_cards_html(apps), unsafe_allow_html=True)
    launch_cards()
    @st.fragment(run_every=60)
    def daily_assignments():
        render_daily_plan(apps)
    daily_assignments()
    with st.container(border=True, key="home_progress"):
        st.markdown('<div class="cm-progress-heading"><span>✦</span>きょうの がんばり</div>', unsafe_allow_html=True)
        if st.button("今日の成果を確認する", key="home_today", type="primary", use_container_width=True):
            _open_today()
            st.rerun()
    st.caption("学習アプリは別のタブで開きます。")


def render_stamp_book(rows: list[dict], target_day: date, truncated: bool) -> None:
    st.markdown(f'<div class="cm-page-heading">{html.escape(date_label(target_day))}のスタンプ</div>',
                unsafe_allow_html=True)
    if not rows:
        st.markdown('''<div class="cm-empty">まだスタンプがありません。<br>チャレンジをおえると、ここにふえていくよ。</div>''',
                    unsafe_allow_html=True)
        return
    counts = {grade: sum(1 for r in rows if normalize_grade(r.get("grade")) == grade) for grade in GRADE_NAMES}
    totals = (("合計", len(rows)), ("金", counts["gold"]), ("銀", counts["silver"]),
              ("銅", counts["bronze"]), ("白", counts["white"]))
    summary = '<div class="cm-stamp-totals">' + "".join(
        f'<div class="cm-total"><span>{label}</span><strong>{value}</strong></div>'
        for label, value in totals) + '</div>'
    st.markdown(summary, unsafe_allow_html=True)
    if truncated:
        st.warning("この日は記録が非常に多いため、先頭1万件まで表示しています。")
    st.markdown(stamp_grid_html(rows), unsafe_allow_html=True)
    st.markdown('**スタンプを おんせいで きいてみよう**')
    components.html(voice_panel(rows), height=160, scrolling=False)
    with st.expander("くわしい学習の記録"):
        details = [{
            "時刻": jst_time(r.get("finished_at")),
            "教科": SUBJECT_NAMES.get(str(r.get("source_app")), str(r.get("source_app") or "学習")),
            "学習内容": str(r.get("category_label") or "学習"),
            "難易度": str(r.get("difficulty") or "—"),
            "正解数": f"{safe_int(r.get('correct_count'))} / {safe_int(r.get('total_count'))}",
            "スタンプ": GRADE_NAMES[normalize_grade(r.get("grade"))] + str(r.get("stamp_char") or "学"),
        } for r in rows]
        st.dataframe(details, hide_index=True, use_container_width=True)


def render_today(url: str, key: str, profile: str, missing: list[str]) -> None:
    st.markdown('<div class="cm-page-heading">今日の成果</div>', unsafe_allow_html=True)
    today = now_jst().date()
    st.markdown(f'<div class="cm-note">{html.escape(date_label(today))} · 日本時間</div>', unsafe_allow_html=True)
    if st.button("最新のスタンプを読み込む", key="refresh_today", use_container_width=True):
        st.session_state.cm_today_requested = True
        st.session_state.cm_today_loaded_for = None
    if not st.session_state.get("cm_today_requested"):
        st.info("「最新のスタンプを読み込む」を押すと、今日獲得したスタンプを表示します。")
        return
    with st.spinner("スタンプを確認しています…"):
        _load_today_if_requested(url, key, profile, missing)
    if st.session_state.get("cm_today_error"):
        st.error(st.session_state.cm_today_error)
        return
    rows = st.session_state.get("cm_today_rows")
    if rows is not None:
        render_stamp_book(rows, today, bool(st.session_state.get("cm_today_truncated")))


def render_history(url: str, key: str, profile: str, missing: list[str]) -> None:
    st.markdown('<div class="cm-page-heading">過去のスタンプ</div>', unsafe_allow_html=True)
    st.markdown('<div class="cm-note">まえの日のがんばりも、消えずに残ります。</div>', unsafe_allow_html=True)
    today = now_jst().date()
    previous = today - timedelta(days=1)
    chosen = st.date_input("見たい日をえらぶ", value=previous, max_value=today,
                           key="cm_history_picker")
    if st.button("この日のスタンプを見る", key="load_history", use_container_width=True):
        st.session_state.cm_history_loaded_for = None
        st.session_state.cm_history_requested_for = chosen
    requested = st.session_state.get("cm_history_requested_for")
    if requested != chosen:
        st.info("日付を選んで「この日のスタンプを見る」を押してください。")
        return
    if st.session_state.get("cm_history_loaded_for") != chosen:
        if missing:
            st.error("Supabase接続設定が不足しています。")
            return
        with st.spinner("スタンプを確認しています…"):
            try:
                rows, truncated = fetch_day(url, key, profile, chosen, st.session_state.get("cm_access_token", ""))
                st.session_state.cm_history_rows = rows
                st.session_state.cm_history_truncated = truncated
                st.session_state.cm_history_error = None
            except RuntimeError as exc:
                st.session_state.cm_history_error = str(exc)
                st.session_state.cm_history_rows = None
        st.session_state.cm_history_loaded_for = chosen
    if st.session_state.get("cm_history_error"):
        st.error(st.session_state.cm_history_error)
        return
    rows = st.session_state.get("cm_history_rows")
    if rows is not None:
        render_stamp_book(rows, chosen, bool(st.session_state.get("cm_history_truncated")))


def _day_transition() -> None:
    """Refresh a long-open tab after Japan's midnight (fragment when available)."""
    day = now_jst().date()
    if st.session_state.cm_jst_day != day:
        st.session_state.cm_jst_day = day
        st.session_state.cm_today_rows = None
        st.session_state.cm_today_loaded_for = None
        st.session_state.cm_today_requested = False
        st.rerun()


def main() -> None:
    st.set_page_config(page_title="ちょこまな | まなびのホーム", page_icon="📚",
                       layout="wide", initial_sidebar_state="collapsed")
    st.markdown(STYLES, unsafe_allow_html=True)
    if "cm_page" not in st.session_state:
        st.session_state.cm_page = "home"
    if "cm_jst_day" not in st.session_state:
        st.session_state.cm_jst_day = now_jst().date()

    _day_transition()
    # In Streamlit >=1.37, a cheap fragment keeps the day separator accurate if
    # the app remains open across Japan midnight. It performs no database calls.
    if hasattr(st, "fragment"):
        @st.fragment(run_every=60)
        def midnight_check():
            _day_transition()
        midnight_check()

    render_header()
    linked = cm_hub_identity()
    if not linked:
        return
    render_navigation()
    if st.session_state.cm_page == "settings":
        render_settings()
        return
    apps = [{**spec, "url": _setting(spec["secret"]),
             "ready": linked and _valid_https_url(_setting(spec["secret"]))} for spec in APP_DEFINITIONS]
    if st.session_state.cm_page == "home":
        render_home(apps)
        return
    if not linked:
        return

    profile = st.session_state["cm_profile"]
    url, key, profile, missing = _db_config()

    if st.session_state.cm_page == "home":
        render_home(apps)
    elif st.session_state.cm_page == "today":
        render_today(url, key, profile, missing)
    elif st.session_state.cm_page == "history":
        render_history(url, key, profile, missing)
    else:
        st.session_state.cm_page = "home"
        render_home(apps)

    if missing:
        with st.expander("接続設定（管理者向け）", expanded=False):
            st.warning("Streamlit Secretsで次の項目を設定してください：" + "、".join(missing))
            st.caption("スタンプはSupabaseのchokomana_stampsテーブルから本人分だけ取得します。")
    elif st.session_state.cm_page in ("today", "history"):
        st.caption("記録の保存は各学習アプリで行います。この画面は参照のみです。")


# ---- CHOCOMANA GUEST IDENTITY: autogenerated, server verified ----
# Shared authentication helpers used only by the stamp pages.
# Tokens remain in the browser storage for the current app origin.
# No service key or refresh token is placed in a URL.
import hashlib
import json
import os
import re
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

import streamlit as st
import streamlit.components.v1 as components

CM_PUBLIC_URL = 'https://keewulninyoeylgflshb.supabase.co'
CM_PUBLIC_KEY = 'sb_publishable_iud9MpcZSxZHzSczRTIDqg_4BNZWQ8g'
CM_SOURCE_KEYS = ('kotoba','soroban','geometry')
CM_TICKET_SECONDS = 900


def cm_secret(name, default=''):
    try: value = st.secrets.get(name)
    except Exception: value = None
    if value is None: value = os.environ.get(name, default)
    return str(value or '').strip()


def cm_api_request(url, method, path, *, key, token=None, payload=None, params=None, timeout=8, prefer=None):
    from urllib.parse import urlencode
    base = url.rstrip('/') + path
    if params: base += '?' + urlencode(params)
    headers = {'apikey': key, 'Accept':'application/json', 'Content-Type':'application/json'}
    if token: headers['Authorization']='Bearer '+token
    elif key and not key.startswith('sb_secret_') and not key.startswith('sb_publishable_'):
        headers['Authorization']='Bearer '+key
    if prefer: headers['Prefer']=prefer
    data=None if payload is None else json.dumps(payload).encode('utf-8')
    req=Request(base,data=data,headers=headers,method=method)
    try:
        with urlopen(req,timeout=timeout) as response:
            raw=response.read()
            return json.loads(raw) if raw else None
    except HTTPError as e:
        raise RuntimeError(f'通信に失敗しました（HTTP {e.code}）') from None
    except (URLError,TimeoutError,OSError):
        raise RuntimeError('接続を確認してください') from None


def cm_validate_guest(access_token):
    if not access_token or not isinstance(access_token,str) or len(access_token)>16000:
        raise ValueError('認証情報がありません')
    url=cm_secret('SUPABASE_URL',CM_PUBLIC_URL)
    key=cm_secret('SUPABASE_PUBLISHABLE_KEY',CM_PUBLIC_KEY)
    user=cm_api_request(url,'GET','/auth/v1/user',key=key,token=access_token)
    if not isinstance(user,dict) or not re.fullmatch(r'[0-9a-f-]{36}',str(user.get('id',''))):
        raise ValueError('利用者IDを確認できません')
    if user.get('is_anonymous') is not True:
        raise ValueError('匿名利用者ではありません')
    return user['id']


def cm_auth_html():
    """Pure JS client using documented GoTrue Auth REST endpoints.
    No CDN; works from the self-hosted Streamlit component origin.
    """
    source=r'''<!doctype html><html lang="ja"><meta charset="utf-8"><style>body{margin:0}</style>
<script>
(()=>{
const url=__URL__,key=__KEY__,storageName='chokomana_guest_auth_2026_01';
const secret={get(){try{return JSON.parse(localStorage.getItem(storageName)||'null')}catch(e){return null}},set(v){localStorage.setItem(storageName,JSON.stringify(v))}};
let sent='';let busy=false;
const emit=v=>window.parent.postMessage({isStreamlitMessage:true,type:'streamlit:setComponentValue',value:v},'*');
async function api(method,path,body,token){
 const resp=await fetch(url+path,{method,headers:{'apikey':key,'Content-Type':'application/json',...(token?{'Authorization':'Bearer '+token}:{})},...(body?{body:JSON.stringify(body)}:{})});
 const json=await resp.json().catch(()=>({}));
 if(!resp.ok)throw new Error('HTTP '+resp.status+(json.error_code?': '+json.error_code:''));
 return json;
}
async function authenticate(){
 if(busy)return;busy=true;
 try{
  let session=secret.get();
  if(session?.access_token && session?.refresh_token){
   try{
    const info=await api('GET','/auth/v1/user',null,session.access_token);
    if(info?.id && info?.is_anonymous===true){emit({status:'ready',access_token:session.access_token});return}
    throw new Error('保存済みIDが一致しません');
   }catch(e){
    try{
     const refreshed=await api('POST','/auth/v1/token?grant_type=refresh_token',{refresh_token:session.refresh_token});
     if(!refreshed.access_token||!refreshed.refresh_token)throw Error('更新できません');
     secret.set(refreshed);emit({status:'ready',access_token:refreshed.access_token});return;
    }catch(ex){emit({status:'error',reason:'保存済みの匿名セッションを更新できません。ブラウザデータを削除せず管理者へお問い合わせください。'});return}
   }
  }
  // New users only. No silent new identity if an old identity cannot be restored.
  session=await api('POST','/auth/v1/signup',{data:{}});
  if(!session.access_token||!session.refresh_token||!session.user?.is_anonymous)throw Error('匿名認証が無効です');
  secret.set(session);emit({status:'ready',access_token:session.access_token});
 }catch(e){emit({status:'error',reason:'匿名利用を開始できません。Supabase Authで「Allow anonymous sign-ins」を有効にしてください。'+String(e.message).slice(0,90)})}
 finally{busy=false}
}
window.addEventListener('message',e=>{if(e.data?.type==='streamlit:render')authenticate()});
window.parent.postMessage({isStreamlitMessage:true,type:'streamlit:componentReady',apiVersion:1},'*');
window.parent.postMessage({isStreamlitMessage:true,type:'streamlit:setFrameHeight',height:0},'*');
setTimeout(authenticate,50);
})();
</script></html>'''
    return source.replace('__URL__',json.dumps(cm_secret('SUPABASE_URL',CM_PUBLIC_URL))).replace('__KEY__',json.dumps(cm_secret('SUPABASE_PUBLISHABLE_KEY',CM_PUBLIC_KEY)))


@st.cache_resource(max_entries=4)
def cm_auth_component(frontend):
    digest=hashlib.sha256(frontend.encode()).hexdigest()[:18]
    folder=Path(tempfile.gettempdir())/('cm_guest_auth_'+digest)
    folder.mkdir(exist_ok=True,parents=True)
    (folder/'index.html').write_text(frontend,encoding='utf-8')
    return components.declare_component('cm_guest_auth_'+digest,path=str(folder))


def cm_guest_identity():
    if not cm_hub_identity():
        st.stop()
    return st.session_state["cm_profile"], ""


def cm_resolve_hub_device(token):
    """Server-only map from a 256-bit browser capability to a learner UUID."""
    from uuid import UUID
    if not isinstance(token, str) or not re.fullmatch(r"[a-f0-9]{64}", token):
        raise ValueError("端末の連携情報を確認できません")
    device_hash = hashlib.sha256(("hub:" + token).encode()).hexdigest()
    url, key = cm_service_config()
    params = {"device_hash": "eq." + device_hash, "select": "profile_id", "limit": "1"}
    rows = cm_api_request(url, "GET", "/rest/v1/chokomana_hub_devices", key=key, params=params)
    if not rows:
        # A competing first request cannot replace an already registered identity.
        cm_api_request(url, "POST", "/rest/v1/chokomana_hub_devices", key=key,
                       payload={"device_hash": device_hash},
                       params={"on_conflict": "device_hash"},
                       prefer="resolution=ignore-duplicates,return=minimal")
        rows = cm_api_request(url, "GET", "/rest/v1/chokomana_hub_devices", key=key, params=params)
    if not isinstance(rows, list) or len(rows) != 1:
        raise RuntimeError("利用者の連携情報を取得できませんでした")
    return str(UUID(rows[0]["profile_id"]))


def cm_hub_device_html():
    """Browser persistence contains a random session token, never a password."""
    return r"""<!doctype html><html><meta charset="utf-8"><body><script>
let loaded=false,lastCommand='';
function snapshot(ack){
 let session=null,legacy=null,ok=true;
 try{session=localStorage.getItem('chokomana_account_session_v1');legacy=localStorage.getItem('chokomana_hub_device_v1')}catch(e){ok=false}
 return {status:'ready',session_token:session,legacy_device_token:legacy,storage_ok:ok,ack:ack||null}
}
function emit(value){parent.postMessage({isStreamlitMessage:true,type:'streamlit:setComponentValue',value,dataType:'json'},'*')}
window.addEventListener('message',e=>{
 if(e.source!==parent||e.data?.type!=='streamlit:render')return;
 const c=e.data.args?.command;
 if(c?.id&&c.id!==lastCommand){
  lastCommand=c.id;let ok=true;
  try{if(c.token)localStorage.setItem('chokomana_account_session_v1',c.token);else localStorage.removeItem('chokomana_account_session_v1')}catch(ex){ok=false}
  const v=snapshot(c.id);v.storage_ok=ok;emit(v);loaded=true;
 }else if(!loaded){loaded=true;emit(snapshot())}
});
parent.postMessage({isStreamlitMessage:true,type:'streamlit:componentReady',apiVersion:1},'*');
parent.postMessage({isStreamlitMessage:true,type:'streamlit:setFrameHeight',height:0},'*');
</script></body></html>"""


def cm_account_username(value):
    name = str(value or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{2,31}", name):
        raise ValueError("ユーザー名は半角英数字で3〜32文字にしてください。「_」「-」「.」も使えます。")
    return name


def cm_password_hash(password, salt=None):
    import secrets
    if not isinstance(password, str) or not 4 <= len(password) <= 128:
        raise ValueError("パスワードは4〜128文字で入力してください。")
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt),
                            n=16384, r=8, p=1, dklen=32).hex()
    return "scrypt$16384$8$1$" + salt + "$" + digest


def cm_password_matches(password, encoded):
    import hmac
    try:
        kind, n, r, p, salt, expected = encoded.split("$")
        if (kind, n, r, p) != ("scrypt", "16384", "8", "1"):
            return False
        if not re.fullmatch(r"[a-f0-9]{32}", salt) or not re.fullmatch(r"[a-f0-9]{64}", expected):
            return False
        # Verification runs even for an unknown username, using a dummy hash.
        actual = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt),
                                 n=16384, r=8, p=1, dklen=32).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, AttributeError):
        return False


def cm_account_request(method, path, payload=None, params=None, prefer=None):
    url, key = cm_service_config()
    if path.startswith("/rpc/"):
        path = "/rest/v1" + path
    return cm_api_request(url, method, path, key=key, payload=payload, params=params, prefer=prefer)


def cm_account_gate(username):
    bucket = hashlib.sha256(("account:" + username).encode()).hexdigest()
    allowed = cm_account_request("POST", "/rpc/chokomana_account_gate", {"bucket_key": bucket})
    if allowed is not True:
        raise ValueError("入力を繰り返したため、10分ほど待ってからお試しください。")
    return bucket


def cm_account_new_session(profile, username, bucket):
    import secrets
    token = secrets.token_hex(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    cm_account_request("POST", "/rest/v1/chokomana_account_sessions", {
        "token_hash": token_hash, "profile_id": profile,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
    }, prefer="return=minimal")
    cm_account_request("PATCH", "/rest/v1/chokomana_auth_limits", {"attempts": 0},
                       {"bucket_hash": "eq." + bucket}, "return=minimal")
    return {"profile_id": profile, "username": username, "token": token}


def cm_register_account(username, password, confirmation, legacy_token=None):
    name = cm_account_username(username)
    if password != confirmation:
        raise ValueError("確認用パスワードが一致していません。もう一度入力してください。")
    if not isinstance(password, str) or not 4 <= len(password) <= 128:
        raise ValueError("パスワードは4〜128文字で入力してください。")
    bucket = cm_account_gate(name)
    encoded = cm_password_hash(password)
    legacy_hash = None
    if isinstance(legacy_token, str) and re.fullmatch(r"[a-f0-9]{64}", legacy_token):
        legacy_hash = hashlib.sha256(("hub:" + legacy_token).encode()).hexdigest()
    result = cm_account_request("POST", "/rpc/chokomana_register_account", {
        "account_name": name, "encoded_password": encoded, "legacy_hash": legacy_hash,
    })
    if not isinstance(result, dict) or result.get("ok") is not True:
        raise ValueError("このユーザー名は使われています。別の名前にするか、「ログイン」を選んでください。")
    return cm_account_new_session(result["profile_id"], name, bucket)


def cm_login_account(username, password):
    name = cm_account_username(username)
    if not isinstance(password, str) or not 1 <= len(password) <= 128:
        raise ValueError("ユーザー名とパスワードを確認してください。")
    bucket = cm_account_gate(name)
    rows = cm_account_request("GET", "/rest/v1/chokomana_accounts", params={
        "username": "eq." + name, "select": "username,profile_id,password_hash", "limit": "1",
    })
    account = rows[0] if isinstance(rows, list) and len(rows) == 1 else None
    encoded = account["password_hash"] if account else "scrypt$16384$8$1$" + "0"*32 + "$" + "0"*64
    matches = cm_password_matches(password, encoded)
    if not account or not matches:
        raise ValueError("ユーザー名とパスワードを確認してください。")
    return cm_account_new_session(account["profile_id"], account["username"], bucket)


def cm_restore_account(token):
    if not isinstance(token, str) or not re.fullmatch(r"[a-f0-9]{64}", token):
        return None
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    rows = cm_account_request("GET", "/rest/v1/chokomana_account_sessions", params={
        "token_hash": "eq." + token_hash, "expires_at": "gt." + datetime.now(timezone.utc).isoformat(),
        "select": "profile_id", "limit": "1",
    })
    if not isinstance(rows, list) or len(rows) != 1:
        return None
    account = cm_account_request("GET", "/rest/v1/chokomana_accounts", params={
        "profile_id": "eq." + str(rows[0]["profile_id"]), "select": "username,profile_id", "limit": "1",
    })
    if not isinstance(account, list) or len(account) != 1:
        return None
    return {**account[0], "token": token}


def cm_change_password(current_password, new_password, confirmation):
    if not isinstance(new_password, str) or not 4 <= len(new_password) <= 128:
        raise ValueError("新しいパスワードは4〜128文字で入力してください。")
    if new_password != confirmation:
        raise ValueError("新しいパスワードと確認用の入力が一致していません。")
    token = st.session_state.get("cm_account_token")
    account = cm_restore_account(token)
    if not account or account["profile_id"] != st.session_state.get("cm_profile"):
        raise ValueError("ログインの有効期限が切れました。もう一度ログインしてください。")
    cm_account_gate(account["username"])
    rows = cm_account_request("GET", "/rest/v1/chokomana_accounts", params={
        "profile_id": "eq." + str(account["profile_id"]),
        "select": "password_hash", "limit": "1",
    })
    if (not isinstance(current_password, str) or not 1 <= len(current_password) <= 128
            or not isinstance(rows, list) or len(rows) != 1
            or not cm_password_matches(current_password, rows[0]["password_hash"])):
        raise ValueError("現在のパスワードが違います。入力を確認してください。")
    changed = cm_account_request("POST", "/rpc/chokomana_change_password", {
        "p_profile": account["profile_id"], "p_expected_hash": rows[0]["password_hash"],
        "p_new_hash": cm_password_hash(new_password),
        "p_session_hash": hashlib.sha256(token.encode()).hexdigest(),
    })
    if changed is not True:
        raise ValueError("変更できませんでした。現在のパスワードとログイン状態を確認してください。")
    for key in list(st.session_state):
        if key.startswith("cm_link_"):
            st.session_state.pop(key, None)


def render_settings():
    changed = st.session_state.pop("cm_password_changed", False)
    if changed:
        for key in ("cm_change_current", "cm_change_new", "cm_change_confirmation"):
            st.session_state.pop(key, None)
    st.markdown("## 設定")
    st.caption("ユーザー名：" + st.session_state.get("cm_account_username", ""))
    if changed:
        st.success("パスワードを変更しました。次回から新しいパスワードでログインできます。")
    render_plan_age()
    # Share the existing account card and widget styles in both browser themes.
    with st.container(border=True, key="cm_account_form"):
        st.markdown("**パスワードを変更**")
        st.caption("ユーザー名と学習記録はそのまま残ります。")
        with st.form("cm_password_change_form", clear_on_submit=False):
            current = st.text_input("現在のパスワード", type="password", max_chars=128,
                                    key="cm_change_current")
            new = st.text_input("新しいパスワード（4文字以上）", type="password", max_chars=128,
                                key="cm_change_new", help="4〜128文字。目のマークで入力を確認できます。")
            confirmation = st.text_input("新しいパスワード（確認用）", type="password", max_chars=128,
                                         key="cm_change_confirmation")
            submitted = st.form_submit_button("パスワードを変更", type="primary", use_container_width=True)
        if submitted:
            try:
                with st.spinner("変更しています…"):
                    cm_change_password(current, new, confirmation)
                st.session_state["cm_password_changed"] = True
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
            except RuntimeError:
                st.error("変更結果を確認できませんでした。新しいパスワードでログインできるか確認してください。")
        st.caption("変更すると、ほかの端末のちょこまなでは再ログインが必要になります。")
    if st.button("ホームへ戻る", key="cm_settings_home", use_container_width=True):
        st.session_state.cm_page = "home"
        st.rerun()


def cm_clear_account_state():
    for key in list(st.session_state):
        if key.startswith(("cm_link_", "cm_today_", "cm_history_", "cm_plan_")) or key in (
            "cm_profile", "cm_account_token", "cm_account_username", "cm_hub_validated_token",
            "cm_change_current", "cm_change_new", "cm_change_confirmation", "cm_password_changed"):
            st.session_state.pop(key, None)
    st.session_state.cm_page = "home"


def cm_set_account(account):
    if st.session_state.get("cm_profile") != account["profile_id"]:
        cm_clear_account_state()
    st.session_state["cm_profile"] = account["profile_id"]
    st.session_state["cm_account_username"] = account["username"]
    st.session_state["cm_account_token"] = account["token"]


def cm_queue_account_command(token):
    from uuid import uuid4
    st.session_state["cm_account_command"] = {"id": str(uuid4()), "token": token}


def cm_account_form(legacy_token):
    if st.session_state.pop("cm_account_clear_fields", False):
        for k in ("cm_login_password", "cm_signup_password", "cm_signup_confirmation"):
            st.session_state.pop(k, None)
    st.markdown('<div class="cm-signin-title">アカウントで学習を保存</div>'
                '<p class="cm-signin-note">メール不要。<br>別の端末でも、同じ記録で使えます。</p>',
                unsafe_allow_html=True)
    action = st.radio("はじめてですか？", ["はじめて使う", "ログイン"], horizontal=True,
                      key="cm_account_mode", label_visibility="collapsed")
    signup = action == "はじめて使う"
    with st.container(border=True, key="cm_account_form"):
        st.markdown("**アカウントをつくる**" if signup else "**学習のつづきから**")
        with st.form("cm_signup_form" if signup else "cm_login_form", clear_on_submit=False):
            username = st.text_input("ユーザー名", key="cm_signup_username" if signup else "cm_login_username",
                                     placeholder="例：rinmaru", max_chars=32,
                                     help="半角英数字3〜32文字。「_」「-」「.」も使えます。大文字と小文字は区別しません。")
            password = st.text_input("パスワード（4文字以上）" if signup else "パスワード", type="password", max_chars=128,
                                     key="cm_signup_password" if signup else "cm_login_password",
                                     help="4文字以上。入力欄の目のマークで確認できます。" if signup else None)
            confirmation = st.text_input("パスワード（確認用）", type="password", max_chars=128,
                                         key="cm_signup_confirmation") if signup else None
            submitted = st.form_submit_button("登録してはじめる" if signup else "ログインする",
                                               type="primary", use_container_width=True)
        if submitted:
            try:
                with st.spinner("登録しています…" if signup else "ログインしています…"):
                    account = (cm_register_account(username, password, confirmation, legacy_token)
                               if signup else cm_login_account(username, password))
                cm_set_account(account)
                cm_queue_account_command(account["token"])
                st.session_state["cm_account_clear_fields"] = True
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
            except RuntimeError:
                st.error("接続できませんでした。入力はそのままで、もう一度お試しください。")
        st.caption("ユーザー名とパスワードを保管してください。メールでの再設定はありません。")
        if signup and legacy_token:
            st.caption("このブラウザに未登録の学習履歴があれば、登録時に引き継ぎます。")


def cm_hub_identity():
    command = st.session_state.get("cm_account_command")
    event = cm_auth_component(cm_hub_device_html())(key="cm_account_browser", command=command, default=None)
    if not event and not command:
        st.caption("ログイン状態を確認しています…")
        return False
    if not isinstance(event, dict):
        event = {}
    if command:
        token = command.get("token")
        if event.get("ack") == command["id"]:
            st.session_state.pop("cm_account_command", None)
    else:
        token = event.get("session_token")
    # A blocked localStorage must not prevent using the account in this session.
    if event.get("storage_ok") is False and not command:
        token = st.session_state.get("cm_account_token")
    account = None
    if token:
        try:
            account = cm_restore_account(token)
        except RuntimeError:
            st.error("ログイン状態を確認できませんでした。もう一度お試しください。")
            if st.button("再試行", key="cm_account_retry"):
                st.rerun()
            return False
        if not account:
            cm_clear_account_state()
            cm_queue_account_command(None)
            st.info("ログインの有効期限が切れました。もう一度ログインしてください。")
    if not account:
        cm_clear_account_state()
        cm_account_form(event.get("legacy_device_token"))
        return False
    cm_set_account(account)
    if st.session_state.pop("cm_account_clear_fields", False):
        for k in ("cm_login_password", "cm_signup_password", "cm_signup_confirmation"):
            st.session_state.pop(k, None)
    if event.get("storage_ok") is False:
        st.caption("このブラウザではログインを保存できません。次回もユーザー名とパスワードでログインできます。")
    with st.expander(account["username"] + " さん（アカウント）"):
        st.caption("このブラウザでは次回から自動ログインします。別の人が使うときはログアウトしてください。")
        if st.button("設定・パスワード変更", key="cm_open_settings", use_container_width=True):
            st.session_state.cm_page = "settings"
            st.rerun()
        if st.button("ログアウト", key="cm_account_logout", use_container_width=True):
            try:
                cm_account_request("PATCH", "/rest/v1/chokomana_account_sessions",
                                   {"expires_at": datetime.now(timezone.utc).isoformat()},
                                   {"token_hash": "eq." + hashlib.sha256(token.encode()).hexdigest()}, "return=minimal")
            except RuntimeError:
                st.error("ログアウトできませんでした。接続を確認して再試行してください。")
                return False
            cm_clear_account_state()
            cm_queue_account_command(None)
            st.session_state["cm_account_mode"] = "ログイン"
            st.rerun()
    return True



def cm_service_config():
    url=cm_secret('SUPABASE_URL',CM_PUBLIC_URL)
    key=cm_secret('SUPABASE_SERVICE_ROLE_KEY') or cm_secret('SUPABASE_SECRET_KEY')
    if not url.startswith('https://') or not key:
        raise RuntimeError('Supabaseのサーバー側接続設定が不足しています')
    return url,key


def cm_issue_ticket(profile,source):
    if source not in CM_SOURCE_KEYS:raise ValueError('未登録のアプリです')
    import secrets
    raw=secrets.token_urlsafe(32)
    url,key=cm_service_config()
    data={'ticket_hash':hashlib.sha256(raw.encode('utf-8')).hexdigest(),'profile_id':profile,
          'source_app':source,'expires_at':(datetime.now(timezone.utc)+timedelta(seconds=CM_TICKET_SECONDS)).isoformat()}
    cm_api_request(url,'POST','/rest/v1/chokomana_launch_tickets',key=key,payload=data,prefer='return=minimal')
    return raw


def cm_consume_ticket(source):
    """Atomically redeem one-time launch code, proof of portal-authenticated user.
    Requires the learning app's own server-side service secret.
    """
    if source not in CM_SOURCE_KEYS:raise ValueError('未登録アプリです')
    ticket=st.query_params.get('cm_launch')
    existing=st.session_state.get('cm_child_profile')
    if existing:
        if ticket:
            try: del st.query_params['cm_launch']
            except Exception:pass
        return existing
    if not ticket or not isinstance(ticket,str) or len(ticket)>256:
        return None
    url,key=cm_service_config()
    params={'ticket_hash':'eq.'+hashlib.sha256(ticket.encode()).hexdigest(),
            'source_app':'eq.'+source,'used_at':'is.null',
            'expires_at':'gt.'+datetime.now(timezone.utc).isoformat(),'select':'profile_id'}
    rows=cm_api_request(url,'PATCH','/rest/v1/chokomana_launch_tickets',key=key,
                        payload={'used_at':datetime.now(timezone.utc).isoformat()},
                        params=params,prefer='return=representation')
    try:del st.query_params['cm_launch']
    except Exception:pass
    if not isinstance(rows,list) or len(rows)!=1:
        raise ValueError('起動リンクが期限切れ、または使用済みです。ちょこまなからもう一度開いてください。')
    st.session_state['cm_child_profile']=str(rows[0]['profile_id'])
    return st.session_state['cm_child_profile']


def cm_child_identity(source):
    """Child can play launched from portal or standalone with an automatic anon ID.
    Server validates identity; no fixed shared profile or public service keys.
    """
    launched=cm_consume_ticket(source)
    if launched:return launched
    profile,_=cm_guest_identity()
    return profile


def cm_launch_url(base,code):
    parsed=urlsplit(base)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('HTTPSの学習アプリURLを設定してください')
    query=dict(parse_qsl(parsed.query,keep_blank_values=True))
    query['cm_launch']=code
    return urlunsplit((parsed.scheme,parsed.netloc,parsed.path,urlencode(query),''))

# Adaptive planning uses observed responses, never medal colors or a language model's guesses.
CM_PLANNER_VERSION = 'adaptive-1'


def cm_plan_rows(table, params):
    """Page a single verified learner's data; never silently analyze a partial history."""
    result = []
    for offset in range(0, 100000, 500):
        rows = cm_account_request('GET', '/rest/v1/' + table,
                                  params={**params, 'offset': str(offset), 'limit': '500'})
        if not isinstance(rows, list):
            raise RuntimeError('invalid learning response')
        result.extend(rows)
        if len(rows) < 500:
            return result
    raise RuntimeError('learning history pagination limit reached')


def cm_plan_settings():
    profile = st.session_state['cm_profile']
    cache = st.session_state.get('cm_plan_settings')
    if cache and cache['profile'] == profile and time.time()-cache.get('at',0)<60:
        return cache['age']
    rows = cm_account_request('GET', '/rest/v1/chokomana_learner_settings', params={
        'profile_id': 'eq.' + profile, 'select': 'age', 'limit': '1'})
    if not isinstance(rows, list):
        raise RuntimeError('invalid settings response')
    age = rows[0]['age'] if rows else None
    st.session_state['cm_plan_settings'] = {'profile': profile, 'age': age, 'at': time.time()}
    return age


def cm_save_plan_age(age):
    if isinstance(age, bool) or not isinstance(age, int) or not 1 <= age <= 100:
        raise ValueError('年齢は1〜100歳で入力してください。')
    profile = st.session_state['cm_profile']
    cm_account_request('POST', '/rest/v1/chokomana_learner_settings', {
        'profile_id': profile, 'age': age, 'updated_at': datetime.now(timezone.utc).isoformat()},
        {'on_conflict': 'profile_id'}, 'resolution=merge-duplicates,return=minimal')
    st.session_state['cm_plan_settings'] = {'profile': profile, 'age': age, 'at': time.time()}
    st.session_state.pop('cm_plan_snapshot', None)


def render_plan_age():
    try:
        age = cm_plan_settings()
    except RuntimeError:
        st.error('年齢の設定を読み込めませんでした。接続を確認して再試行してください。')
        return
    with st.container(border=True, key='cm_age_card'):
        st.markdown('**1日の学習時間**')
        with st.form('cm_age_form'):
            chosen = st.number_input('年齢（歳）', min_value=1, max_value=100,
                                     value=age, step=1, placeholder='年齢を入力', key='cm_plan_age_input')
            st.caption('1日の目安は年齢×10分。例：5歳なら50分です。')
            save = st.form_submit_button('年齢を保存', type='primary', use_container_width=True)
        if save:
            try:
                cm_save_plan_age(chosen)
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
            except RuntimeError:
                st.error('保存できませんでした。もう一度お試しください。')


def cm_plan_date(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return parsed if parsed.tzinfo else None
    except (ValueError, TypeError):
        return None


def cm_plan_union(spans):
    merged = []
    for start, end in sorted(spans):
        if end <= start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def cm_plan_menus(catalog, age):
    import math
    latest = {}
    for row in sorted(catalog, key=lambda r: (r.get('published_at', ''), r.get('content_version', ''))):
        if row.get('entry_type') != 'menu' or row.get('source_app') not in SUBJECT_NAMES:
            continue
        latest[(row['source_app'], row['entry_id'])] = row
    menus = []
    for row in latest.values():
        p = row.get('payload') or {}
        if p.get('is_active') is False:
            continue
        if p.get('age_min') is not None and age < p['age_min']:
            continue
        if p.get('age_max') is not None and age > p['age_max']:
            continue
        # Only catalog entries with a real duration and known selection path can be assigned.
        duration = p.get('estimated_duration_ms')
        if not isinstance(duration, (float, int)) or not math.isfinite(duration) or not 0 < duration <= 14400000:
            continue
        if not isinstance(p.get('selection_instructions'), list) or not p['selection_instructions']:
            continue
        menus.append({**p, 'source_app': row['source_app'], 'menu_id': row['entry_id'],
                      'content_version': row['content_version']})
    return menus


def cm_plan_analyze(events, menus, profile, today):
    """First scored submissions only; app support/retries never count as unaided mastery."""
    from collections import defaultdict
    from statistics import median
    unique = {}
    for e in events:
        if e.get('profile_id') != profile:
            raise RuntimeError('learning owner mismatch')
        if e['event_id'] in unique and unique[e['event_id']] != e:
            raise RuntimeError('learning event conflict')
        unique[e['event_id']] = e
    rows = sorted(unique.values(), key=lambda e: (e['occurred_at'], e.get('sequence', 0), e['event_id']))
    starts, items, ends, spans, unknown, reloaded = {}, {}, {}, defaultdict(list), set(), set()
    for e in rows:
        aid = (e['source_app'], e['attempt_id']); p = e.get('payload') or {}
        if e['event_type'] == 'session_started':
            starts[aid] = e
        elif e['event_type'] == 'item_presented':
            items[(aid, e.get('occurrence_id'))] = e
        elif e['event_type'] == 'session_ended':
            ends[aid] = e
        elif e['event_type'] == 'session_resumed' and p.get('reason') == 'page_reload':
            reloaded.add(aid)
        elif e['event_type'] == 'time_interval_closed':
            a, b = cm_plan_date(p.get('start_at')), cm_plan_date(p.get('end_at'))
            active = p.get('active_ms')
            if p.get('timing_quality') != 'complete' or active is None:
                unknown.add(aid)
            if active == 0:
                continue
            if (not a or not b or b <= a or not isinstance(active, (int, float))
                    or abs((b - a).total_seconds()*1000 - active) > 2):
                unknown.add(aid)
                continue
            spans[aid].append((a, b))
    observations, seen = defaultdict(lambda: defaultdict(list)), set()
    for e in rows:
        if e['event_type'] != 'response_submitted':
            continue
        aid = (e['source_app'], e['attempt_id']); p = e.get('payload') or {}
        item = items.get((aid, e.get('occurrence_id'))); start = starts.get(aid)
        if not item or not start:
            continue
        ip, sp = item['payload'], start['payload']
        key = (aid, e.get('occurrence_id'), p.get('substep_id'))
        if key in seen:
            continue
        seen.add(key)
        if (p.get('response_index') != 1 or ip.get('parent_occurrence_id')
                or ip.get('presentation_kind') == 'retry' or p.get('response_status') != 'answered'
                or p.get('assessment_method') != 'automatic' or not isinstance(p.get('is_correct'), bool)):
            continue
        support = p.get('support_before_response')
        clean = (isinstance(support, dict) and support.get('hint_count') == 0
                 and all(support.get(k) is False for k in ('explanation_seen', 'answer_seen', 'worked_example_seen'))
                 and support.get('parent_help') is not True and ip.get('answer_exposed_before') is False)
        cohort = json.dumps([sp.get('settings_snapshot'), sp.get('mode'), p.get('input_method')], sort_keys=True)
        menu_key = (e['source_app'], sp.get('menu_id'), start['content_version'])
        when = cm_plan_date(e['occurred_at'])
        if when:
            observations[menu_key][cohort].append({'day': when.astimezone(TOKYO).date(),
                'correct': p['is_correct'], 'clean': clean, 'aid': aid,
                'question': e.get('question_id'), 'time': when})
    stats, duration_samples = {}, defaultdict(lambda: defaultdict(list))
    for key, cohorts in observations.items():
        # Do not merge unlike settings/modes/input methods; use the most recently observed cohort.
        values = max(cohorts.values(), key=lambda v: v[-1]['time'])[-40:]
        clean = [v for v in values if v['clean']]
        rate = sum(v['correct'] for v in clean) / len(clean) if clean else None
        aids = {v['aid'] for v in clean}
        recent_aid = values[-1]['aid']
        last_set = [v for v in values if v['aid'] == recent_aid]
        last_rate = sum(v['correct'] and v['clean'] for v in last_set) / len(last_set)
        # Questions must vary, with evidence in multiple actual attempts, before advancing.
        mastered = (len(clean) >= 8 and len(aids) >= 2 and len({v['question'] for v in clean if v['question']}) >= 4
                    and rate >= .9 and last_rate >= .85)
        weak = len(last_set) >= 4 and last_rate < .7
        daily = defaultdict(list)
        for v in values:
            daily[v['day']].append(v)
        streak = 0
        for day in sorted(daily):
            vv = daily[day]
            if sum(v['correct'] and v['clean'] for v in vv)/len(vv) >= .85:
                streak += 1
            else:
                streak = 0
        interval = (1, 3, 7, 14, 30)[min(max(streak-1, 0), 4)]
        last_day = max(daily)
        stats[key] = {'mastered': mastered, 'weak': weak, 'accuracy': rate,
            'posterior': (1+sum(v['correct'] for v in clean))/(2+len(clean)),
            'due': last_day + timedelta(days=1 if weak else interval), 'last_day': last_day,
            'attempts': len(aids), 'count': len(clean)}
    for aid, end in ends.items():
        start = starts.get(aid)
        if not start or end['payload'].get('status') != 'completed' or aid in unknown or aid in reloaded or not spans[aid]:
            continue
        sp = start['payload']
        condition = json.dumps([sp.get('settings_snapshot'), sp.get('planned_question_count'), sp.get('mode')], sort_keys=True)
        ms = round(sum((b-a).total_seconds()*1000 for a,b in cm_plan_union(spans[aid])))
        key = (start['source_app'], sp.get('menu_id'), start['content_version'])
        duration_samples[key][condition].append((end['occurred_at'], ms, sp.get('planned_question_count')))
    durations = {}
    for key, cohorts in duration_samples.items():
        values = max(cohorts.values(), key=lambda v: max(x[0] for x in v))
        recent = sorted(values, reverse=True)[:10]
        if len(recent) >= 3:
            durations[key] = {'ms': round(median(x[1] for x in recent)), 'count': len(recent), 'question_count': recent[0][2]}
    lo = datetime.combine(today, datetime.min.time(), TOKYO)
    hi = lo + timedelta(days=1)
    daily_spans = [(max(a,lo), min(b,hi)) for ss in spans.values() for a,b in ss if b>lo and a<hi]
    measured = round(sum((b-a).total_seconds()*1000 for a,b in cm_plan_union(daily_spans)))
    menu_map = {(m['source_app'],m['menu_id'],m['content_version']):m for m in menus}
    estimated, missing = 0, 0
    today_counts = defaultdict(int)
    completed = defaultdict(int)
    for aid, end in ends.items():
        start = starts.get(aid)
        if start and end['payload'].get('status')=='completed':
            completed[(start['source_app'],start['payload'].get('menu_id'),start['content_version'])] += 1
        when = cm_plan_date(end['occurred_at']); start = starts.get(aid)
        if not start or not when or when.astimezone(TOKYO).date()!=today or end['payload'].get('status')!='completed':
            continue
        key = (start['source_app'], start['payload'].get('menu_id'), start['content_version'])
        today_counts[key] += 1
        if aid in unknown or aid in reloaded or not spans[aid]:
            missing += 1
            m = menu_map.get(key)
            if m:
                actual = sum((min(b,hi)-max(a,lo)).total_seconds()*1000 for a,b in cm_plan_union(spans[aid]) if b>lo and a<hi)
                estimated += max(0, m['estimated_duration_ms'] - actual)
    partial_today = any(aid in unknown and any(b>lo and a<hi for a,b in ss) for aid,ss in spans.items())
    return {'stats': stats, 'durations': durations, 'spent_ms': measured+round(estimated),
            'measured_ms': measured, 'estimated_ms': round(estimated), 'missing_time': missing,
            'partial_time': partial_today, 'today_counts': today_counts, 'completed': completed}


# Explicit planning prerequisites between independent soroban tracks. These are conservative
# portal policy, not facts inferred from the catalog's null prerequisite fields.
CM_TRACK_GATES = {
 'soroban:calculation:mul': ['soroban:kuku:1'],
 'soroban:calculation:div': ['soroban:calculation:mm1'],
 'soroban:calculation:advanced': ['soroban:calculation:ba5x4', 'soroban:calculation:bs5x4'],
 'soroban:tutorial:mul': ['soroban:kuku:1'],
 'soroban:tutorial:div': ['soroban:calculation:mm1'],
 'soroban:hosu:add': ['soroban:calculation:ba1'],
 'soroban:hosu:sub': ['soroban:calculation:bs1'],
}


def cm_plan_candidates(menus, analysis, today):
    from collections import defaultdict
    groups = defaultdict(list); stats = analysis['stats']; candidates = []
    def key(m): return (m['source_app'],m['menu_id'],m['content_version'])
    known = {m['menu_id']:stats.get(key(m),{}) for m in menus}
    for m in menus:
        if 'reading_aloud' in m.get('mode_options', []):
            continue  # Read-aloud alone is not evidence of mastery.
        groups[(m['source_app'],m.get('progression_group_id') or m['menu_id'])].append(m)
    for (_, group), mm in sorted(groups.items()):
        mm.sort(key=lambda m: (m.get('difficulty_order') or 0,m['menu_id']))
        observed = [m for m in mm if key(m) in stats or ('learn' in m.get('mode_options',[]) and analysis['completed'].get(key(m),0))]
        if not observed and not all(known.get(mid,{}).get('mastered') for mid in CM_TRACK_GATES.get(group, [])):
            continue
        # A demonstrated higher level can be the starting point; don't force every old level.
        frontier = max(observed,key=lambda m:m.get('difficulty_order') or 0) if observed else mm[0]
        fs = stats.get(key(frontier), {})
        learned = 'learn' in frontier.get('mode_options',[]) and analysis['completed'].get(key(frontier),0)>0
        if fs.get('mastered') or learned:
            allowed_next = set(frontier.get('next_menu_ids') or [])
            nexts = [m for m in mm if m['menu_id'] in allowed_next]
            if nexts:
                frontier = nexts[0]
        chosen = [frontier] + [m for m in observed if key(m)!=key(frontier) and stats.get(key(m),{}).get('due',today+timedelta(days=1))<=today]
        for m in chosen:
            ss = stats.get(key(m), {})
            if ss.get('mastered') and ss.get('due', today)>today:
                continue
            required = m.get('prerequisite_skill_ids')
            if required:
                demonstrated = set(s for row in menus if stats.get(key(row),{}).get('mastered') for s in row.get('skill_ids',[]) if len(row.get('skill_ids',[]))==1)
                if not set(required)<=demonstrated:
                    continue
            if ss.get('weak'):
                reason, score = 'もういちど練習', 110 + 20*(1-ss['posterior'])
            elif ss and ss.get('due',today)<=today:
                reason, score = '思い出す復習', 105 + min(15,(today-ss['due']).days)
            elif key(m)!=key(mm[0]) and not ss:
                reason, score = ('学んだ教材のつづき' if 'learn' in m.get('mode_options',[]) else '得意をのばす・次の単元'), 100
            else:
                reason, score = ('理解をたしかめる', 75) if ss else ('はじめの力だめし', 70)
            estimate = analysis['durations'].get(key(m))
            measured = estimate and estimate['question_count']==m.get('question_count_default')
            duration = estimate['ms'] if measured else m['estimated_duration_ms']
            if duration<=0:
                continue
            candidates.append({**m, 'duration_ms':int(duration), 'duration_basis':'measured' if measured else 'provisional',
                'reason':reason, 'score':score, 'key':key(m), 'accuracy':ss.get('accuracy')})
    return candidates


def cm_build_daily_plan(candidates, remaining_ms, today_counts):
    """Bounded knapsack in 10-second units, rounding UP to enforce the duration cap."""
    import math
    capacity = max(0, int(remaining_ms//10000))
    if capacity==0:
        return []
    # 1..100 years accepted in settings; use sparse DP and cap study-item count naturally.
    dp = {0:(0.0, [])}
    ordered = sorted(candidates,key=lambda c:(c['source_app'],c['menu_id']))
    for candidate in ordered:
        units = math.ceil(candidate['duration_ms']/10000)
        completed = today_counts.get(candidate['key'],0)
        choices = max(0,3-completed)
        previous = list(dp.items())
        for used,(value,path) in previous:
            for count in range(1,choices+1):
                total = used+units*count
                if total>capacity:
                    break
                bonus = sum((1,.65,.35)[completed+i] for i in range(count))
                quality = value+candidate['score']*units*bonus
                if total not in dp or quality>dp[total][0]:
                    dp[total]=(quality,path+[(candidate,count)])
    # Fit at least 95% if achievable; otherwise return the honest shortfall.
    lower = math.ceil(remaining_ms*.95/10000)
    feasible = [u for u in dp if u>=lower]
    best = max(feasible,key=lambda u:(dp[u][0],u)) if feasible else max(dp)
    return [{**c,'repetitions':count,'planned_ms':c['duration_ms']*count} for c,count in dp[best][1]]


def cm_load_daily_plan(age, allowed_sources=None):
    profile = st.session_state['cm_profile']; today = now_jst().date()
    catalog = cm_plan_rows('chokomana_learning_catalog', {'entry_type':'eq.menu',
        'select':'entry_type,entry_id,source_app,content_version,payload,published_at',
        'order':'source_app,entry_id,content_version'})
    menus = cm_plan_menus(catalog,age)
    rows = cm_plan_rows('chokomana_learning_events', {'profile_id':'eq.'+profile,
        'select':'event_id,profile_id,source_app,content_version,attempt_id,occurrence_id,question_id,sequence,occurred_at,event_type,payload',
        'order':'occurred_at,event_id'})
    analysis = cm_plan_analyze(rows,menus,profile,today)
    target = age*10*60000
    remaining = max(0,target-analysis['spent_ms'])
    candidates = cm_plan_candidates(menus,analysis,today)
    if allowed_sources is not None:
        candidates = [c for c in candidates if c['source_app'] in allowed_sources]
    reached = analysis['spent_ms'] >= target*.95
    items = [] if reached else cm_build_daily_plan(candidates,remaining,analysis['today_counts'])
    planned = sum(i['planned_ms'] for i in items)
    payload = {'planner_version':CM_PLANNER_VERSION,'age':age,'target_ms':target,
        'spent_ms':analysis['spent_ms'],'measured_ms':analysis['measured_ms'],
        'estimated_ms':analysis['estimated_ms'],'missing_time':analysis['missing_time'],
        'partial_time':analysis['partial_time'],'remaining_ms':remaining,
        'planned_ms':planned,'items':items,'sources':sorted({m['source_app'] for m in menus}),
        'reached':reached, 'sufficient':reached or planned>=remaining*.95,
        'generated_at':datetime.now(timezone.utc).isoformat()}
    cm_account_request('POST','/rest/v1/chokomana_daily_plans',{
        'profile_id':profile,'study_date':today.isoformat(),'payload':payload,
        'updated_at':payload['generated_at']}, {'on_conflict':'profile_id,study_date'},
        'resolution=merge-duplicates,return=minimal')
    return payload


def cm_minutes(ms):
    return f'{max(0,ms)/60000:.1f}'.rstrip('0').rstrip('.')


def cm_plan_items_html(items):
    parts = []
    for n,item in enumerate(items,1):
        label = html.escape(str(item.get('label',item['menu_id'])))
        category = html.escape(str(item.get('category_label','')))
        reason = html.escape(item['reason'])
        steps = ' → '.join(html.escape(str(x)) for x in item['selection_instructions'])
        repeats = f' × {item["repetitions"]}回' if item['repetitions']>1 else ''
        source = html.escape(SUBJECT_NAMES[item['source_app']])
        basis = '本人の実測' if item['duration_basis']=='measured' else '仮の目安'
        parts.append(f'<li class="cm-plan-item"><span class="cm-plan-number">{n}</span><div>'
            f'<div class="cm-plan-subject">{source} · {category}</div><h3>{label}{repeats}</h3>'
            f'<p>{reason}</p><p>約{cm_minutes(item["planned_ms"])}分 · {basis}</p>'
            f'<p class="cm-plan-path">えらぶ順：{steps}</p></div></li>')
    return '<ol class="cm-plan-list">'+''.join(parts)+'</ol>'


def render_daily_plan(apps):
    with st.container(border=True,key='cm_daily_plan'):
        st.markdown('### きょう やること')
        try:
            age = cm_plan_settings()
        except RuntimeError:
            st.error('学習設定を読み込めませんでした。')
            return
        if age is None:
            st.info('年齢を設定すると、今日やる学習を自動で選びます。')
            render_plan_age()
            return
        refresh = st.button('学習記録を更新',key='cm_plan_refresh',use_container_width=True)
        cached = st.session_state.get('cm_plan_snapshot')
        cache_key = (st.session_state['cm_profile'],now_jst().date().isoformat(),age)
        if refresh or not cached or cached['key']!=cache_key or time.time()-cached['at']>60:
            try:
                with st.spinner('学習記録から、今日の内容を選んでいます…'):
                    payload = cm_load_daily_plan(age,{a['id'] for a in apps if a['ready']})
                cached = {'key':cache_key,'at':time.time(),'payload':payload}
                st.session_state['cm_plan_snapshot']=cached
            except (RuntimeError,ValueError,KeyError,TypeError):
                st.error('学習記録を読み込めませんでした。「学習記録を更新」で再試行してください。')
                st.caption('読み込みに失敗した記録を、未学習として扱うことはありません。')
                return
        p = cached['payload']
        st.markdown(f'**{age}歳 · 1日{age*10}分**　／　学習済み 約{cm_minutes(p["spent_ms"])}分')
        if not p['reached']:
            st.caption(f'このあとの予定：約{cm_minutes(p["planned_ms"])}分（残りの目安 {cm_minutes(p["remaining_ms"])}分）')
        if p['missing_time'] or p['partial_time']:
            st.caption('未計測の時間があります。完了した学習は単元の目安時間で補っており、残り時間は暫定です。')
        if p['reached']:
            st.success('きょうの目安にとどいたよ！')
        elif p['items']:
            st.markdown(cm_plan_items_html(p['items']),unsafe_allow_html=True)
            sources = {i['source_app'] for i in p['items']}
            for app in apps:
                if app['id'] in sources:
                    if app['ready']:
                        try:
                            st.link_button(app['title']+'を開く ↗',_make_launch_link(app),use_container_width=True)
                        except (RuntimeError,ValueError):
                            st.error(app['title']+'の起動リンクを作れませんでした。')
                    else:
                        st.warning(app['title']+'のURLが未設定です。接続設定を確認してください。')
            st.caption('アプリを開き、一覧の「えらぶ順」で単元を選んでください。単元への直接起動には未対応です。')
        if not p['sufficient']:
            st.warning(f'今の進度で選べる単元では、残りの目安に約{cm_minutes(p["remaining_ms"]-p["planned_ms"])}分足りません。'
                       '時間を埋めるために未習得の上級単元を追加しません。')
        pending = [SUBJECT_NAMES[s] for s in SUBJECT_NAMES if s not in p['sources']]
        if pending:
            st.caption('単元データ未登録：'+'・'.join(pending)+'。登録後、自動選定の対象になります。')
        with st.expander('選び方・時間の目安について'):
            st.write('初回回答の正答率とアプリ内のヒント利用を単元別に確認します。十分な成績が複数回そろうと次の単元へ進み、つまずいた単元は繰り返します。')
            st.write('復習間隔は正答が続くと1→3→7→14→30日へ延ばし、つまずくと翌日に戻します。効果を保証する日数ではなく、成績に応じて調整する初期設定です。')
            st.write('年齢×10分はこのアプリの設定です。休憩は学習時間に含めず、まとめて続ける必要はありません。予定は残り時間の95〜100％を目指し、1日の目安の95％に達したら終了にします。同じ単元は1日3回までにします。')
            st.write('所要時間は保証値ではありません。同じ条件の完了記録が3回以上そろうと直近10回までの実測中央値を使い、それまでは仮の目安を表示します。')
            st.caption('学習ログから判定する適応型モデルです。生成AIへのデータ送信やAPIの追加料金はありません。画面外での助力や内面の理解は断定しません。')


if __name__ == "__main__":
    main()
