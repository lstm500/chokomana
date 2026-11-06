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
  CHOCOMANA_PROFILE_ID = "<same exact learner ID as every study app>"

Optional Streamlit Secrets:
  KOTOBA_APP_URL = "https://...streamlit.app"
  SOROBAN_APP_URL = "https://...streamlit.app"
  GEOMETRY_APP_URL = "https://...streamlit.app"

Security: service/secret key stays in Streamlit's Python process. Protect this
hub's Streamlit deployment with private access if it contains children's data.
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
    url = _setting("SUPABASE_URL", DEFAULT_SUPABASE_URL).rstrip("/")
    key = _setting("SUPABASE_SERVICE_ROLE_KEY") or _setting("SUPABASE_SECRET_KEY")
    profile = _setting("CHOCOMANA_PROFILE_ID")
    missing = []
    if not _valid_https_url(url):
        missing.append("SUPABASE_URL（HTTPSのProject URL）")
    if not key:
        missing.append("SUPABASE_SERVICE_ROLE_KEY または SUPABASE_SECRET_KEY")
    if not profile:
        missing.append("CHOCOMANA_PROFILE_ID")
    return url, key, profile, missing


def fetch_day(url: str, secret_key: str, profile_id: str, target_day: date) -> tuple[list[dict], bool]:
    """Fetch only one learner/day, with server-only authentication and paging.

    study_date is a generated JST date in PostgreSQL. No new rows are written.
    """
    if not _valid_https_url(url) or not secret_key or not profile_id:
        raise ValueError("Supabase接続設定または学習者IDがありません")
    rows = []
    base = url.rstrip("/") + "/rest/v1/" + TABLE_NAME
    headers = {
        "apikey": secret_key,
        "Accept": "application/json",
        "User-Agent": "chokomana-hub/1.0",
    }
    # Legacy service_role keys are JWTs. New sb_secret_ keys use the API key
    # header and must not be passed as non-JWT Bearer tokens.
    if not secret_key.startswith("sb_secret_"):
        headers["Authorization"] = "Bearer " + secret_key

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
    return '<div class="cm-stamp-grid">' + ''.join(cards) + '</div>'


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
.tile.active{transform:translateY(-6px) scale(1.12);box-shadow:0 5px 0 #799af5,inset 0 4px 9px #fff7}
.controls{display:flex;gap:9px}.controls button{border:0;border-radius:13px;padding:13px 11px;font-weight:800;font-size:14px;cursor:pointer}
#play{flex:1;background:#305fa7;color:white}#stop{background:#f1f3f7;color:#3d5167;min-width:78px}
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
</style>
"""


def render_header() -> None:
    st.markdown('''<div class="cm-brand"><div class="cm-logo">ち</div>
      <div><h1>ちょこまな</h1><p>あそんで、まなんで、スタンプをあつめよう</p></div></div>''',
      unsafe_allow_html=True)


def render_navigation() -> None:
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
                    st.session_state.cm_game = None
                st.rerun()


def _open_today() -> None:
    st.session_state.cm_page = "today"
    st.session_state.cm_game = None
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
        rows, truncated = fetch_day(url, key, profile, day)
        st.session_state.cm_today_rows = rows
        st.session_state.cm_today_truncated = truncated
        st.session_state.cm_today_error = None
    except RuntimeError as exc:
        st.session_state.cm_today_error = str(exc)
        st.session_state.cm_today_rows = None


def render_home(apps: list[dict]) -> None:
    st.markdown('<div class="cm-hero"><h2>きょうは なにを まなぶ？</h2>'
                '<p>すきなきょうかをえらんで、チャレンジしよう。</p></div>',
                unsafe_allow_html=True)
    st.markdown('<div class="cm-page-heading">あそべる学習アプリ</div>', unsafe_allow_html=True)
    cols = st.columns(3, gap="medium")
    for col, app in zip(cols, apps):
        with col:
            with st.container(border=True):
                block = (f'<div class="cm-app-art"><div class="icon">{html.escape(app["icon"])}</div>'
                         f'<div class="name">{html.escape(app["title"])}</div>'
                         f'<div class="tag">{html.escape(app["tag"])}</div></div>')
                st.markdown(block, unsafe_allow_html=True)
                if app["ready"]:
                    if st.button("あそぶ", key="launch_" + app["id"],
                                 type="primary", use_container_width=True):
                        st.session_state.cm_game = app["id"]
                        st.session_state.cm_page = "game"
                        st.rerun()
                else:
                    st.button("まだ準備中", key="disabled_" + app["id"],
                              disabled=True, use_container_width=True,
                              help=f'Secretsに {app["secret"]} を設定してください')
    st.markdown('<div class="cm-page-heading">きょうの がんばり</div>', unsafe_allow_html=True)
    st.markdown('<div class="cm-note">チャレンジがおわると、各アプリがスタンプを保存します。</div>', unsafe_allow_html=True)
    if st.button("今日の成果を確認する", key="home_today", type="primary", use_container_width=True):
        _open_today()
        st.rerun()


def render_game(apps: list[dict]) -> None:
    app = next((x for x in apps if x["id"] == st.session_state.get("cm_game")), None)
    if not app or not app["ready"]:
        st.session_state.cm_page = "home"
        st.warning("アプリのURLが設定されていません。")
        return
    st.markdown(f'<div class="cm-page-heading">{html.escape(app["title"])}</div>', unsafe_allow_html=True)
    st.markdown('<div class="cm-note">学習アプリは独立して動作します。終わったら「今日の成果」を開いてください。</div>',
                unsafe_allow_html=True)
    left, right = st.columns(2, gap="small")
    with left:
        if st.button("← ほかの教科を選ぶ", use_container_width=True):
            st.session_state.cm_page = "home"
            st.session_state.cm_game = None
            st.rerun()
    with right:
        st.link_button("別のタブでひらく ↗", url=app["url"], use_container_width=True)
    st.caption("アプリが表示されない場合は「別のタブでひらく」を使ってください。")
    components.iframe(app["url"], height=775, scrolling=True)
    if st.button("今日の成果を確認する", key="game_today", type="primary", use_container_width=True):
        _open_today()
        st.rerun()


def render_stamp_book(rows: list[dict], target_day: date, truncated: bool) -> None:
    st.markdown(f'<div class="cm-page-heading">{html.escape(date_label(target_day))}のスタンプ</div>',
                unsafe_allow_html=True)
    if not rows:
        st.markdown('''<div class="cm-empty">まだスタンプがありません。<br>チャレンジをおえると、ここにふえていくよ。</div>''',
                    unsafe_allow_html=True)
        return
    counts = {grade: sum(1 for r in rows if normalize_grade(r.get("grade")) == grade) for grade in GRADE_NAMES}
    numbers = st.columns(5, gap="small")
    for col, (label, value) in zip(numbers, (("合計", len(rows)), ("金", counts["gold"]),
                                           ("銀", counts["silver"]), ("銅", counts["bronze"]),
                                           ("白", counts["white"]))):
        with col:
            st.metric(label, value, border=True)
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
                rows, truncated = fetch_day(url, key, profile, chosen)
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
    if "cm_game" not in st.session_state:
        st.session_state.cm_game = None
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
    render_navigation()
    url, key, profile, missing = _db_config()
    apps = [{**spec, "url": _setting(spec["secret"]),
             "ready": _valid_https_url(_setting(spec["secret"]))} for spec in APP_DEFINITIONS]

    if st.session_state.cm_page == "home":
        render_home(apps)
    elif st.session_state.cm_page == "game":
        render_game(apps)
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
            st.caption("スタンプはSupabaseの既存chokomana_stampsテーブルから取得します。"
                       "秘密鍵をGitHubやブラウザ画面に貼り付けないでください。")
    elif st.session_state.cm_page in ("today", "history"):
        st.caption("記録の保存は各学習アプリで行います。この画面は参照のみです。")


if __name__ == "__main__":
    main()
