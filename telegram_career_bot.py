import os
import sys
import time
import json
import re
import urllib.parse
from pathlib import Path
import requests

# Ensure imports work from current project root
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))

try:
    from portal_app import get_career_ai_response, get_curated_somali_it_jobs, is_spam_or_invalid
except ImportError:
    def get_career_ai_response(msg):
        return "Salamaat! Waxaan ahay Kaaliyaha Baahiye AI & Shaqo Raadiyaha Dhalinyarada Soomaaliyeed. Waxaan kaa caawin karaa dhammaan fursadaha shaqo, gaar ahaan IT-ga, CV ATS ah, iyo buugaagta Isbar."
    def get_curated_somali_it_jobs():
        return []
    def is_spam_or_invalid(msg):
        return False, ""

def load_env_file():
    env_path = BASE_DIR / ".env"
    if env_path.exists():
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k and k not in os.environ:
                            os.environ[k] = v
        except Exception:
            pass

load_env_file()

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("CRITICAL: TELEGRAM_BOT_TOKEN is not set in environment or .env file!")

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
PRIMARY_DOMAIN = "https://isbar-ai.com"
FALLBACK_DOMAIN = "https://auto-jobs-applier-aih-awk-live.vercel.app"
WEB_APP_URL = PRIMARY_DOMAIN
GITHUB_REPO_URL = "https://github.com/Faratoon/Shaqo-Raadiyahaaga-Gaarka-Ah"
SUBSTACK_URL = "https://somalilibrary.substack.com"
DHEGEYSO_BUUG_SUBSTACK = "https://dhegeysobuug.substack.com/"
YOUTUBE_URL = "https://www.youtube.com/@Mfaratoon"
SHARE_TEXT = urllib.parse.quote("🔥 Fursadaha Shaqo, Akadeemiyada Isbar & Maamulka Telegram (isbar-ai.com)! Ka faa'iideyso @Baahiyebot 🚀")

# Database & Telegram Management Configuration
TG_DATA_FILE = BASE_DIR / "telegram_management_data.json"
VULGAR_WORDS = [
    "wasmo", "siil", "gus", "futada", "fck", "bitch", "shit",
    "dhuuq", "qaniis", "dhillo", "naago", "futo", "aflagaado"
]

def load_tg_data():
    if TG_DATA_FILE.exists():
        try:
            with open(TG_DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"users": {}, "channels": {}, "groups": {}, "knowledge_docs": []}

def save_tg_data(data):
    try:
        with open(TG_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[!] Error saving tg data: {e}", flush=True)

def get_user_record(user_id, referrer_id=None):
    data = load_tg_data()
    uid = str(user_id)
    now = time.time()
    
    if uid not in data["users"]:
        data["users"][uid] = {
            "created_at": now,
            "referrals": [],
            "unlocked_permanent": False
        }
        
        # Credit referrer if valid
        if referrer_id and str(referrer_id) != uid:
            ref_uid = str(referrer_id)
            if ref_uid in data["users"]:
                if uid not in data["users"][ref_uid]["referrals"]:
                    data["users"][ref_uid]["referrals"].append(uid)
                    if len(data["users"][ref_uid]["referrals"]) >= 10:
                        data["users"][ref_uid]["unlocked_permanent"] = True
                    save_tg_data(data)
                    # Notify referrer
                    try:
                        ref_count = len(data["users"][ref_uid]["referrals"])
                        if ref_count >= 10:
                            send_message(int(ref_uid), "🌟 <b>HAMBALYO HEER SARE AH!</b>\n\nWaxaad keentay <b>10 qof</b>! Waxaa laguu furay <b>Maamulka Telegram Fasax Buuxa oo Bilaash ah (Lifetime Permanent Free Access)</b>!")
                        else:
                            send_message(int(ref_uid), f"🎉 <b>Qof cusub ayaa ku soo biiray link-gaaga!</b>\n\nWaxaad keentay: <b>{ref_count}/10 qof</b>. Markaad gaarto 10 qof waxaad helaysaa Fasax Joogto ah oo Bilaash ah!")
                    except Exception:
                        pass
        save_tg_data(data)

    user = data["users"][uid]
    elapsed_days = int((now - user.get("created_at", now)) / 86400)
    days_left = max(0, 40 - elapsed_days)
    referrals_count = len(user.get("referrals", []))
    is_permanent = user.get("unlocked_permanent", False) or (referrals_count >= 10)
    is_active = is_permanent or (days_left > 0)

    return {
        "user_id": uid,
        "days_left": days_left,
        "referrals_count": referrals_count,
        "is_permanent": is_permanent,
        "is_active": is_active,
        "referral_link": f"https://t.me/Baahiyebot?start=ref_{uid}"
    }

def delete_message(chat_id, message_id):
    url = f"{API_URL}/deleteMessage"
    try:
        requests.post(url, json={"chat_id": chat_id, "message_id": message_id}, timeout=10)
    except Exception:
        pass

def configure_bot_menu_button():
    """Sets the Telegram Chat Menu Button to open the Mini App natively."""
    url = f"{API_URL}/setChatMenuButton"
    payload = {
        "menu_button": {
            "type": "web_app",
            "text": "📱 isbar-ai.com",
            "web_app": {"url": WEB_APP_URL}
        }
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        data = res.json()
        print(f"[*] Telegram Chat Menu Button set: {data.get('ok')}", flush=True)
    except Exception as e:
        print(f"[!] Error setting menu button: {e}", flush=True)

def send_photo(chat_id, photo_path, caption=None, reply_markup=None, parse_mode="HTML"):
    url = f"{API_URL}/sendPhoto"
    data = {"chat_id": chat_id}
    if caption:
        data["caption"] = caption
        data["parse_mode"] = parse_mode
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    try:
        p = Path(photo_path)
        if p.exists():
            with open(p, "rb") as f:
                res = requests.post(url, data=data, files={"photo": f}, timeout=25)
                data_res = res.json()
                if data_res.get("ok"):
                    print(f"[*] Photo banner sent to {chat_id}", flush=True)
                    return data_res
                print(f"[!] sendPhoto failed: {data_res}", flush=True)
    except Exception as e:
        print(f"[!] Error sending photo: {e}", flush=True)
    if caption:
        return send_message(chat_id, caption, reply_markup, parse_mode=parse_mode)
    return None

def send_message(chat_id, text, reply_markup=None, parse_mode="HTML"):
    url = f"{API_URL}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": False
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        res = requests.post(url, json=payload, timeout=15)
        data = res.json()
        if not data.get("ok") and parse_mode:
            payload.pop("parse_mode", None)
            res = requests.post(url, json=payload, timeout=15)
            data = res.json()
        print(f"[*] Message sent to {chat_id} (OK: {data.get('ok')})", flush=True)
        return data
    except Exception as e:
        print(f"[!] Error sending message to {chat_id}: {e}", flush=True)
        return None

def answer_callback_query(callback_query_id, text=None):
    url = f"{API_URL}/answerCallbackQuery"
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception:
        pass

FIELD_NAMES = {
    "finance": "📊 Maamul & Xisaabaad",
    "sales": "📞 Customer Care & Iib",
    "health": "🏥 Caafimaad & NGO",
    "edu": "📚 Waxbarasho & Macallin",
    "tech": "💻 IT & Farsamo",
    "logistics": "📦 Logistics & Gaadiid"
}

LOCATION_NAMES = {
    "muqdisho": "🇸🇴 Muqdisho",
    "hargeysa": "🇸🇴 Hargeysa & Puntland",
    "nairobi": "🇰🇪 Nairobi (Kenya)",
    "remote": "🌐 Remote (Online Guriga)",
    "canada": "🇨🇦 Diaspora (Canada & Global)"
}

EXP_NAMES = {
    "entry": "🌱 Ku cusub / Qalin-jabin (Entry)",
    "mid": "💼 1 ilaa 3 Sano oo Khibrad ah",
    "senior": "🏆 3+ Sano (Khibrad Sare)"
}

def get_main_keyboard():
    return {
        "inline_keyboard": [
            # Row 1: Full-width Web App button
            [
                {"text": "🚀 Fur Web App-ka (isbar-ai.com)", "web_app": {"url": WEB_APP_URL}}
            ],
            # Row 2: Prominent Interactive Quiz & All Jobs
            [
                {"text": "🎯 Quiz: Ii Raadi Shaqadayda 🧭", "callback_data": "quiz_q1"},
                {"text": "💼 Dhammaan Shaqooyinka 🔥", "callback_data": "menu_jobs"}
            ],
            # Row 3: Tools & Telegram Management
            [
                {"text": "⚡ Dhis CV (ATS)", "callback_data": "menu_cv"},
                {"text": "🤖 Maamulka Telegram", "callback_data": "menu_tg_admin"}
            ],
            # Row 4: 2-column Learning & Mentorship
            [
                {"text": "📚 Buugaagta Isbar", "callback_data": "menu_academy"},
                {"text": "📅 Ballan Live ah", "callback_data": "menu_booking"}
            ],
            # Row 5: 2-column Public Info & Community
            [
                {"text": "📞 Xidhiidhka & Taageerada", "callback_data": "menu_contact"},
                {"text": "📢 Baahi / Share", "callback_data": "menu_broadcast"}
            ],
            # Row 6: Open Source GitHub Showcase (100% Free & Open Source)
            [
                {"text": "⭐ GitHub (100% Free & Open Source)", "url": GITHUB_REPO_URL}
            ]
        ]
    }

def handle_start(chat_id, first_name):
    welcome_text = f"""🦅 <b>Shaqo Baahiye (@Baahiyebot)</b>

Ku soo dhowow <b>{first_name}</b>!
Madasha fursadaha shaqo (Maamul, Xisaabaad, Caafimaad, Iib, IT & Remote), CV ATS ah, iyo buugaagta Isbar.

🧭 <b>Shaqo ma raadinaysaa?</b> Guji <i>'🎯 Quiz: Ii Raadi Shaqadayda'</i> si 3 tallaabo laguu caawiyo!"""

    banner_path = BASE_DIR / "assets" / "shaqo_baahiye_banner.png"
    if banner_path.exists():
        send_photo(chat_id, banner_path, caption=welcome_text, reply_markup=get_main_keyboard())
    else:
        send_message(chat_id, welcome_text, get_main_keyboard())

def handle_jobs(chat_id):
    jobs = get_curated_somali_it_jobs()
    text = """💼 <b>Fursadaha Shaqada ee Hadda Bannaan:</b>
<i>(Soomaaliya, Bariga Afrika & Remote)</i>

Shaqo Baahiye wuxuu kuu raadinayaa dhammaan qeybaha: Maamul, Iib, Caafimaad, Waxbarasho, IT & Remote.\n\n"""
    
    for idx, j in enumerate(jobs[:5], 1):
        text += f"<b>{idx}. {j['title']}</b>\n"
        text += f"🏢 {j['company']} &bull; 📍 {j['location']}\n"
        text += f"🔗 <a href='{j['job_url']}'>Codsashada Tooska ah</a>\n\n"

    markup = {
        "inline_keyboard": [
            [{"text": "🎯 Quiz: Ii Raadi Shaqadayda 🧭", "callback_data": "quiz_q1"}],
            [{"text": "📱 Baadh Dhammaan Shaqooyinka (Web App)", "web_app": {"url": f"{WEB_APP_URL}#jobsSection"}}],
            [
                {"text": "🇸🇴 Soomaaliya & Bariga Afrika", "web_app": {"url": f"{WEB_APP_URL}#jobsSection"}},
                {"text": "🌐 Remote & Canada", "web_app": {"url": f"{WEB_APP_URL}#jobsSection"}}
            ],
            [{"text": "🔙 Ku noqo Menu-ga", "callback_data": "menu_main"}]
        ]
    }
    send_message(chat_id, text, markup)

def handle_quiz_step1(chat_id):
    text = """🎯 <b>Quiz: Ii Raadi Shaqada Ku Habboon (Tallaabada 1/3)</b> 🧭

Dooro xirfadda ama qeybta aad ugu jeceshahay inaad ka shaqeyso:"""
    markup = {
        "inline_keyboard": [
            [
                {"text": "📊 Maamul & Xisaabaad", "callback_data": "quiz_f_finance"},
                {"text": "📞 Customer Care & Iib", "callback_data": "quiz_f_sales"}
            ],
            [
                {"text": "🏥 Caafimaad & NGO", "callback_data": "quiz_f_health"},
                {"text": "📚 Waxbarasho & Macallin", "callback_data": "quiz_f_edu"}
            ],
            [
                {"text": "💻 IT & Farsamo", "callback_data": "quiz_f_tech"},
                {"text": "📦 Logistics & Gaadiid", "callback_data": "quiz_f_logistics"}
            ],
            [
                {"text": "🔙 Ku noqo Menu-ga", "callback_data": "menu_main"}
            ]
        ]
    }
    send_message(chat_id, text, markup)

def handle_quiz_step2(chat_id, field):
    f_name = FIELD_NAMES.get(field, "Qeybta aad dooratay")
    text = f"""📍 <b>Quiz: Goobta aad Joogto ama Doonayso (Tallaabada 2/3)</b> 🌍

Doorka aad xiiseyso: <b>{f_name}</b>
Hadda dooro goobta aad shaqada ka raadinayso:"""
    markup = {
        "inline_keyboard": [
            [
                {"text": "🇸🇴 Muqdisho", "callback_data": f"quiz_l_{field}_muqdisho"},
                {"text": "🇸🇴 Hargeysa & Puntland", "callback_data": f"quiz_l_{field}_hargeysa"}
            ],
            [
                {"text": "🇰🇪 Nairobi (Kenya)", "callback_data": f"quiz_l_{field}_nairobi"},
                {"text": "🌐 Remote (Online Guriga)", "callback_data": f"quiz_l_{field}_remote"}
            ],
            [
                {"text": "🇨🇦 Diaspora (Canada & Global)", "callback_data": f"quiz_l_{field}_canada"}
            ],
            [
                {"text": "🔙 Dib u noqo", "callback_data": "quiz_q1"}
            ]
        ]
    }
    send_message(chat_id, text, markup)

def handle_quiz_step3(chat_id, field, location):
    f_name = FIELD_NAMES.get(field, "Qeybta")
    l_name = LOCATION_NAMES.get(location, "Goobta")
    text = f"""🎓 <b>Quiz: Heerka Khibraddaada (Tallaabada 3/3)</b> 💼

Doorka: <b>{f_name}</b> | Goobta: <b>{l_name}</b>
Intee in le'eg ayay le'eg tahay khibraddaadu?"""
    markup = {
        "inline_keyboard": [
            [
                {"text": "🌱 Ku cusub / Qalin-jabin (Entry)", "callback_data": f"quiz_r_{field}_{location}_entry"}
            ],
            [
                {"text": "💼 1 ilaa 3 Sano oo Khibrad ah", "callback_data": f"quiz_r_{field}_{location}_mid"}
            ],
            [
                {"text": "🏆 3+ Sano (Khibrad Sare)", "callback_data": f"quiz_r_{field}_{location}_senior"}
            ],
            [
                {"text": "🔙 Dib u noqo", "callback_data": f"quiz_f_{field}"}
            ]
        ]
    }
    send_message(chat_id, text, markup)

def handle_quiz_result(chat_id, field, location, exp):
    f_name = FIELD_NAMES.get(field, field)
    l_name = LOCATION_NAMES.get(location, location)
    e_name = EXP_NAMES.get(exp, exp)

    loc_query = "Muqdisho" if location == "muqdisho" else ("Hargeysa" if location == "hargeysa" else ("Nairobi" if location == "nairobi" else "Remote"))
    matched = get_curated_somali_it_jobs(term=field, location=loc_query)

    if exp == "entry":
        exp_tip = "💡 <b>Talo Qalin-jabiyaha:</b> CV-gaaga ku caddee maadooyinka aad ugu fiicnayd jaamacadda, mashruucyadii aad qabatay, tababarrada (internships), iyo luuqadaha."
    elif exp == "mid":
        exp_tip = "💡 <b>Talo Khibradda Dhexe:</b> CV-gaaga ku cabbir natiijooyin la taaban karo oo tiro leh (tusaale: 'Waxaan maareeyay xisaabaadka 100+ macaamiil ah')."
    else:
        exp_tip = "💡 <b>Talo Khibradda Sare:</b> Muuji hoggaamintaada, maaraynta kooxaha shaqada, iyo xallinta dhibaatooyinka waaweyn ee ganacsiga."

    text = f"""🎉 <b>Natiijada Quiz-kaaga Shaqo! 🧭</b>

• Doorka: <b>{f_name}</b>
• Goobta: <b>{l_name}</b>
• Khibradda: <b>{e_name}</b>

{exp_tip}

🔥 <b>Fursadaha Kuugu Habboon ee Hadda Bannaan:</b>\n\n"""

    for idx, j in enumerate(matched[:3], 1):
        text += f"<b>{idx}. {j['title']}</b>\n"
        text += f"🏢 {j['company']} &bull; 📍 {j['location']}\n"
        text += f"🔗 <a href='{j['job_url']}'>Codsashada Tooska ah</a>\n\n"

    markup = {
        "inline_keyboard": [
            [{"text": "⚡ Dhis CV Ku Habboon (ATS)", "callback_data": "menu_cv"}],
            [{"text": "📅 Qabso Ballan Live ah (Mentorship)", "callback_data": "menu_booking"}],
            [{"text": "🔄 Dib u bilaaw Quiz-ka", "callback_data": "quiz_q1"}],
            [{"text": "🔙 Ku noqo Menu-ga", "callback_data": "menu_main"}]
        ]
    }
    send_message(chat_id, text, markup)

def handle_cv(chat_id):
    text = """⚡ <b>Diyaarinta CV ATS ah & Wareysiga:</b>

• 📄 <b>ATS Resume (1-Page):</b> Qaab nadiif ah oo nidaamyada shirkadaha u aqbalaan si toos ah.
• 📝 <b>Cover Letter:</b> Warqad codsi oo ku habboon doorkaaga.
• 🎯 <b>STAR Method:</b> Qaabka guusha ee looga jawaabo wareysiyada."""

    markup = {
        "inline_keyboard": [
            [{"text": "⚡ Dhis & Falanqee CV (Web App)", "web_app": {"url": f"{WEB_APP_URL}#assessSection"}}],
            [{"text": "📄 Soo Degso Resume Template (PDF)", "url": f"{WEB_APP_URL}/download/resume"}],
            [{"text": "🔙 Ku noqo Menu-ga", "callback_data": "menu_main"}]
        ]
    }
    send_message(chat_id, text, markup)

def handle_academy(chat_id):
    text = """📚 <b>Akadeemiyada Isbar & Buugaagta:</b>

📖 <b>Buugaagta Isbar (Af-Soomaali):</b>
• 💻 <b>ISBAR COMPUTER</b> ($5) — Windows 11, Office, Photoshop
• 👨‍💻 <b>ISBAR PROGRAMMING</b> ($5) — Web, Python, Database
• 🧠 <b>ISBAR AI BASIC</b> ($7) — AI, Automation & Ganacsiga
• 🤖 <b>ISBAR Prompts</b> — 🎁 <b>Bilaash</b>

📬 <b>Hel 2 Buug oo Bilaash ah (Free):</b>
Ku biir warsidaha <a href="https://dhegeysobuug.substack.com/">dhegeysobuug.substack.com</a> si aad <b>2 Buug oo Bilaash ah</b> si toos ah ugu hesho inbox-kaaga!"""

    markup = {
        "inline_keyboard": [
            [{"text": "📬 Hel 2 Buug oo Free ah (Substack)", "url": DHEGEYSO_BUUG_SUBSTACK}],
            [{"text": "📱 Gal Akadeemiyada Isbar (Web App)", "web_app": {"url": f"{WEB_APP_URL}#coursesHubSection"}}],
            [
                {"text": "💬 Dalbo Buug (WhatsApp)", "url": "https://wa.me/15873064137?text=Salamaat%20Mohamed,%20waxaan%20rabaa%20buug%20Isbar"},
                {"text": "🎁 ChatGPT Prompts (Free)", "web_app": {"url": f"{WEB_APP_URL}#coursesHubSection"}}
            ],
            [{"text": "🔙 Ku noqo Menu-ga", "callback_data": "menu_main"}]
        ]
    }
    send_message(chat_id, text, markup)

def handle_booking(chat_id):
    text = """📅 <b>Ballan Live ah & Mentorship (1-on-1):</b>

Kulan toos ah (Google Meet / Zoom) oo aad la yeelanayso <b>Mohamed Yasin</b>:
• ✅ La-talin jihada shaqada & xirfadda
• ✅ Dib-u-eegista CV-gaaga & Tababarka Wareysiga
• ✅ Hagidda Koorsooyinka AI Automation

📍 <b>Edmonton, Canada 🇨🇦 & Online Global</b>"""

    markup = {
        "inline_keyboard": [
            [{"text": "📅 Qabso Ballan Live ah (Web App)", "web_app": {"url": f"{WEB_APP_URL}#bookingSection"}}],
            [{"text": "💬 WhatsApp Toos ah (+1 587-306-4137)", "url": "https://wa.me/15873064137?text=Salamaat%20Mohamed,%20waxaan%20rabaa%20ballan%20live%20ah"}],
            [{"text": "🔙 Ku noqo Menu-ga", "callback_data": "menu_main"}]
        ]
    }
    send_message(chat_id, text, markup)

def handle_contact(chat_id):
    text = """📞 <b>Xidhiidhka & Taageerada (Support & Contacts):</b>

Dooro nooca caawinaad ee aad doonayso:

🤖 <b>1. Kaaliyaha AI (Bot Chat):</b>
Wuxuu si toos ah kaaga caawinayaa raadinta shaqooyinka, talooyinka CV-ga, iyo buugaagta. Halkan toos ugu qor su'aashaada!

👤 <b>2. Qof Dhab ah (Human Support):</b>
Haddii aad u baahan tahay qof kula hadla, kala xidhiidh <b>Mohamed Yasin</b> toos:
👉 <b>Telegram:</b> @MFARATOON
👉 <b>WhatsApp:</b> +1 (587) 306-4137

📬 <b>3. Buugaagta Bilaashka ah:</b>
<a href="https://dhegeysobuug.substack.com/">dhegeysobuug.substack.com</a> (2 Buug oo Free ah)"""

    markup = {
        "inline_keyboard": [
            [
                {"text": "🤖 La Hadal Kaaliyaha AI (Chat)", "callback_data": "contact_ai_chat"},
                {"text": "👤 Human Support (@MFARATOON)", "url": "https://t.me/MFARATOON"}
            ],
            [
                {"text": "📱 WhatsApp Toos ah", "url": "https://wa.me/15873064137?text=Salamaat%20Mohamed,%20waxaan%20doonayaa%20caawinaad"},
                {"text": "📬 Hel 2 Buug Free", "url": DHEGEYSO_BUUG_SUBSTACK}
            ],
            [
                {"text": "📺 YouTube (@Mfaratoon)", "url": YOUTUBE_URL},
                {"text": "🌐 isbar-ai.com", "url": PRIMARY_DOMAIN}
            ],
            [{"text": "🔙 Ku noqo Menu-ga", "callback_data": "menu_main"}]
        ]
    }
    send_message(chat_id, text, markup)

def handle_tg_admin(chat_id, user_id=None):
    uid = user_id or chat_id
    rec = get_user_record(uid)
    status_text = "⭐ <b>Fasax Joogto ah (Bilaash Weligaa!)</b>" if rec["is_permanent"] else f"⏳ <b>40 Cisho Free Trial ({rec['days_left']} Maalmood baa haray)</b>"

    text = f"""🤖 <b>Maamulka Fasalada & Channels-ka Telegram:</b>

{status_text} | 👥 Referral: <b>{rec['referrals_count']}/10 qof</b>

• 🛡️ <b>Fasalada & Groups:</b> Soo dhoweyn, ilaalinta anshaxa, word filter & kaaliyaha <code>/ask</code>.
• 📢 <b>Channels-ka:</b> Casharrada English Tutor & fursadaha shaqo.
• 🎁 <b>Fasaxa:</b> Keen 10 qof oo fur Fasax Joogto ah weligaa!"""

    markup = {
        "inline_keyboard": [
            [
                {"text": "🛡️ Maamulka Fasalada & Groups", "callback_data": "tg_groups"},
                {"text": "📢 Channels & English Tutor", "callback_data": "tg_channels"}
            ],
            [
                {"text": "🎁 Xaaladdaada & Referral Link", "callback_data": "tg_referral"},
                {"text": "🤝 Xallinta Khilaafaadka", "callback_data": "tg_conflict"}
            ],
            [
                {"text": "📚 Soo Dir Manhaj / Custom Docs", "callback_data": "tg_docs"}
            ],
            [
                {"text": "🔙 Ku noqo Menu-ga Weyn", "callback_data": "menu_main"}
            ]
        ]
    }
    send_message(chat_id, text, markup)

def handle_tg_groups(chat_id):
    text = """🛡️ <b>Maamulka Fasalada & Groups-ka (Classroom Shield):</b>

Sida aad ugu xirayso bot-ka fasalkaaga ama group-kaaga:

1. ➕ <b>Ku dar Bot-ka:</b> Ku dar <code>@Baahiyebot</code> group-ka ama fasalkaaga.
2. 👑 <b>Ka dhig Admin:</b> Sii rukhsadda <i>'Delete Messages'</i> si uu u tirtiro spam-ka iyo aflagaadada.
3. ⚡ <b>Shaqooyinka Otomaatiga ah:</b>
   • <b>Soo dhoweyn:</b> Arday kasta oo cusub wuxuu siinayaa fariin soo dhoweyn iyo xeerarka fasalka.
   • <b>Word Filter:</b> Erayada qadafka ah iyo links-ka spam-ka ah si degdeg ah ayuu u tirtirayaa.
   • <b>Kaaliyaha Su'aalaha:</b> Ardaydu waxay qori karaan <code>/ask [su'aasha]</code> AI-ga ayaana uga jawaabaya.

<i>Tijaabi hadda adoo ku daraya group-kaaga!</i>"""
    markup = {
        "inline_keyboard": [
            [{"text": "➕ Ku Dar Group (Direct)", "url": "https://t.me/Baahiyebot?startgroup=true"}],
            [{"text": "🤝 Xallinta Khilaafaadka", "callback_data": "tg_conflict"}],
            [{"text": "🔙 Ku noqo Maamulka", "callback_data": "menu_tg_admin"}]
        ]
    }
    send_message(chat_id, text, markup)

def handle_tg_channels(chat_id):
    text = """📢 <b>Channels-ka & Casharrada English Tutor:</b>

Bot-ku wuxuu diyaarin karaa oo channels-kaaga ugu baahin karaa casharro heerarkoodu kala duwan yihiin:

🟢 <b>Heerka 1aad (Beginners):</b> Salaanta, erayada maalinlaha ah, iyo wada-hadalka fudud.
🟡 <b>Heerka 2aad (Intermediate):</b> Naxwaha (Grammar), xilliyada (Tenses), iyo qaladaadka caadiga ah.
🔵 <b>Heerka 3aad (Advanced & Career):</b> Erayada xirfadeed ee wareysiyada shaqada (Job Interviews) iyo idioms.
💻 <b>IT Daily Tips:</b> Qoraallo maalinle ah oo ku saabsan Programming, AI, iyo fursadaha shaqo.

<i>Guji mid ka mid ah hoos si aad u eegto tusaale cashar diyaarsan:</i>"""
    markup = {
        "inline_keyboard": [
            [
                {"text": "🟢 Heerka 1: Beginners", "callback_data": "tg_lesson_beg"},
                {"text": "🟡 Heerka 2: Intermediate", "callback_data": "tg_lesson_int"}
            ],
            [
                {"text": "🔵 Heerka 3: Job & Tech", "callback_data": "tg_lesson_adv"},
                {"text": "💻 IT Daily Tip", "callback_data": "tg_lesson_it"}
            ],
            [
                {"text": "🔙 Ku noqo Maamulka", "callback_data": "menu_tg_admin"}
            ]
        ]
    }
    send_message(chat_id, text, markup)

def handle_tg_lesson(chat_id, level):
    if level == "beginner":
        text = """🇬🇧 <b>Casharka 1aad (Beginners): Salaanta & Erayada Maalinlaha ah</b>

📚 <b>Erayo Muhiim ah (Vocabulary):</b>
• <b>Good morning:</b> Subax wanaagsan
• <b>How are you doing?</b> Sidee tahay / xaaladaadu sidee tahay?
• <b>I am learning English:</b> Waxaan baranayaa af Ingiriisiga
• <b>Thank you very much:</b> Aad iyo aad baad u mahadsan tahay
• <b>Have a wonderful day:</b> Maalin cajiib ah qaado

💬 <b>Wada-sheekeysi Fudud (Dialogue):</b>
A: <i>"Good morning, Ahmed! How is your study going?"</i>
B: <i>"Good morning! Everything is going great, thank you."</i>

🎯 <b>Layli (Quick Task):</b>
Sidee Ingiriis ahaan loogu dhahaa: <i>"Waxaan rabaa inaan shaqo helo"</i>?
👉 <b>Jawaabta saxda ah:</b> <i>"I want to find a job."</i>"""
    elif level == "intermediate":
        text = """🇬🇧 <b>Casharka 2aad (Intermediate): Present Perfect vs Past Simple</b>

📚 <b>Xeerka Naxwaha (Grammar Rule):</b>
• <b>Past Simple:</b> Wax dhacay waqti hore oo dhamaaday (Specific finished time).
  Tusaale: <i>"I completed the IT certificate yesterday."</i> (Shalay ayaan dhameeyay shahaadada).
• <b>Present Perfect:</b> Wax dhacay oo saameyntoodu wali taagan tahay ama waqtiga aan la cayimin.
  Tusaale: <i>"I have built three AI bots."</i> (Waxaan dhisay saddex bot oo AI ah).

💬 <b>Qaladka Badan ee La Sameeyo:</b>
❌ <i>"I have seen him yesterday."</i> (Khalad!)
✅ <i>"I saw him yesterday."</i> (Sax!).

🎯 <b>Layli (Quiz):</b>
Buuxi meesha bannaan: <i>"She _____ (work) in Mogadishu for two years."</i>
👉 <b>Jawaabta:</b> <i>"has worked"</i> ama <i>"worked"</i>."""
    elif level == "advanced":
        text = """🇬🇧 <b>Casharka 3aad (Advanced & Tech Careers): Wareysiyada Shaqada (Job Interviews)</b>

📚 <b>Erayada Awoodda Leh ee CV-ga & Wareysiga (Power Verbs):</b>
• <b>Collaborate:</b> Wada-shaqeyn kooxeed yeelasho.
• <b>Troubleshoot:</b> Baaris iyo xallinta cilladaha farsamo.
• <b>Implement:</b> Hirgelinta nidaam ama qorshe cusub.
• <b>Streamline:</b> Fududeynta iyo habeynta howl socotay.

💬 <b>Tusaalaha Jawaab Wareysi (STAR Method):</b>
<i>"In my previous project, I collaborated with the tech team to troubleshoot networking issues and streamline customer support."</i>
(Mashruucii hore, waxaan la shaqeeyay kooxda farsamada si aan u xalliyo cilladaha network-ka una fududeeyo adeegga macaamiisha).

💡 <b>Talo Dahabi ah:</b> Had iyo jeer natiijada la taaban karo ku muuji tiro (tusaale: 'improved efficiency by 30%')."""
    else: # IT tip
        text = """💻 <b>Talo Maalinle ah ee IT-ga & AI Automation:</b>

🚀 <b>Maxay tahay sababta Python & API ay muhiim ugu yihiin dhalinta shaqo doonka ah?</b>
Shirkadaha casriga ah maanta ma shaqaaleeyaan qof hawlaha gacanta ku qabta kaliya; waxay raadinayaan qof fahamsan sida loo otomaatigyeeyo (automate) shaqooyinka soo noqnoqda.

🛠️ <b>Aaladaha ugu muhiimsan ee maanta la rabo:</b>
1. <b>N8n & Make:</b> Isku xirka WhatsApp, Telegram, iyo CRM.
2. <b>OpenAI API:</b> Dhisidda chatbots caqliyeed oo macaamiisha u jawaaba 24/7.
3. <b>FastAPI / Flask:</b> Dhisidda adeegyo fudud oo online ah.

⭐ Repository-ga mashruucan waa 100% Free & Open Source oo qof kasta wuu ka baran karaa!"""

    markup = {
        "inline_keyboard": [
            [{"text": "📢 Baahi Casharkan (Share)", "url": f"https://t.me/share/url?url=https://t.me/Baahiyebot&text={urllib.parse.quote(text[:300])}"}],
            [{"text": "🔙 Ku noqo Channels-ka", "callback_data": "tg_channels"}]
        ]
    }
    send_message(chat_id, text, markup)

def handle_tg_referral(chat_id, user_id=None):
    uid = user_id or chat_id
    rec = get_user_record(uid)
    ref_link = rec["referral_link"]
    status_str = "⭐ <b>Fasax Buuxa oo Bilaash ah (Permanent Free)</b>" if rec["is_permanent"] else f"⏳ <b>40 Cisho Free Trial ({rec['days_left']} Maalmood baa kuu haray)</b>"

    text = f"""🎁 <b>Xaaladdaada Fasaxa & Referral-ka:</b>

{status_str}
👥 Dadka aad keentay: <b>{rec['referrals_count']}/10 qof</b>

🚀 <b>Sidee ku helaysaa Fasax Joogto ah oo Bilaash ah?</b>
Haddii aad link-gaaga u share-gareyso asxaabtaada ama group-yada, <b>10 qof</b> oo kasta oo ku soo biirta, waxaad helaysaa Fasax Buuxa oo Bilaash ah oo aad weligaa ku maamulan karto bot-kan!

🔗 <b>Link-gaaga gaarka ah ee Referral-ka:</b>
<code>{ref_link}</code>"""

    share_url = f"https://t.me/share/url?url={urllib.parse.quote(ref_link)}&text={urllib.parse.quote('🚀 Ku biir Shaqo Baahiye (@Baahiyebot) - Hel shaqooyinka IT-ga, CV ATS ah, iyo maamulka fasalada Telegram!')}"
    markup = {
        "inline_keyboard": [
            [{"text": "📤 Share-garee Link-gaaga (1-Click)", "url": share_url}],
            [{"text": "🔙 Ku noqo Maamulka", "callback_data": "menu_tg_admin"}]
        ]
    }
    send_message(chat_id, text, markup)

def handle_tg_conflict(chat_id):
    text = """🤝 <b>Xallinta Khilaafaadka & Ilaalinta Anshaxa Fasalada:</b>

Fasalada iyo group-yada Telegram marka arday badani isugu timaado, waxaa muhiim ah in loo maamulo si xirfadaysan:

1. ⚖️ <b>Xeerka Dhexdhexaadnimada:</b>
   • Ha qaadan dhinac go'an haddii ardaydu is-qabtaan; ku hagi ujeedka waxbarashada iyo casharka.
2. 🚫 <b>Digniin Shakhsi ah (Private Warning):</b>
   • Qofka anshax-xumada la yimaada, fariintiisa waa la tirtirayaa waxaana loo dirayaa digniin shakhsi ah intaan laga saarin group-ka.
3. 🕊️ <b>Qoraal Nabadeyn ah (Mediation Message):</b>
   • Bot-ku wuxuu si toos ah u dirayaa fariin dejin ah: <i>"Walaalayaal, fasalkan waxaa loo furay barasho iyo horumar, fadlan aan is-dhowrno oo wada-hadalka ku ekeyno casharka."</i>
4. 🔇 <b>Xaddidaadda Qoraalka (Mute):</b>
   • Hadii dooddu sii kululaato, admin-ku wuxuu xiri karaa qoraalka muddo 15 daqiiqo ah si jawigu u qaboobo."""
    markup = {
        "inline_keyboard": [
            [{"text": "🛡️ Maamulka Groups-ka", "callback_data": "tg_groups"}],
            [{"text": "🔙 Ku noqo Maamulka", "callback_data": "menu_tg_admin"}]
        ]
    }
    send_message(chat_id, text, markup)

def handle_tg_docs(chat_id):
    text = """📚 <b>Soo Dir Manhajkaaga ama Xogtaada (Custom Knowledge Base):</b>

Ma rabtaa in bot-ka <b>@Baahiyebot</b> uu si gaar ah ardaydaada ugu sharaxo casharradaada iyo manhajkaaga?

1. 📄 <b>Noocyada Xogta La Ogolyahay:</b>
   • Qoraal toos ah (Syllabus, Casharro, Su'aalo & Jawaabo).
   • Faylal PDF ama Text ah oo ku saabsan koorsadaada.
2. 📩 <b>Sida Loo Soo Diro:</b>
   • Toos ugu soo dir email-ka rasmiga ah: <code>Suxufi34@gmail.com</code>
   • Ama WhatsApp toos ah: <code>+1 (587) 306-4137</code> (Mohamed Yasin)
3. ⚡ <b>Dhaqangelinta:</b>
   • Waxaan xogtaada toos ugu xiraynaa AI-ga bot-ka si ardaydaada fasalka kaliya loogu siiyo jawaabo ku saleysan manhajkaaga!"""
    markup = {
        "inline_keyboard": [
            [{"text": "💬 WhatsApp Toos ah (Mohamed Yasin)", "url": "https://wa.me/15873064137?text=Salamaat%20Mohamed,%20waxaan%20rabaa%20inaan%20soo%20diro%20manhajka%20fasalkayga"}],
            [{"text": "🔙 Ku noqo Maamulka", "callback_data": "menu_tg_admin"}]
        ]
    }
    send_message(chat_id, text, markup)

def handle_broadcast(chat_id):
    text = """📢 <b>Baahinta Fursadaha (Channels & Groups):</b>

Waxaad shaqooyinkan, buugaagta, iyo koorsooyinka bilaashka ah la wadaagi kartaa asxaabtaada ama channel-kaaga Telegram:"""

    markup = {
        "inline_keyboard": [
            [{"text": "📤 Share garee (One-Click)", "url": f"https://t.me/share/url?url=https://t.me/Baahiyebot&text={SHARE_TEXT}"}],
            [{"text": "⭐ Eeg GitHub Repository", "url": GITHUB_REPO_URL}],
            [{"text": "🔙 Ku noqo Menu-ga", "callback_data": "menu_main"}]
        ]
    }
    send_message(chat_id, text, markup)

def process_callback_query(callback_query):
    cq_id = callback_query.get("id")
    data = callback_query.get("data")
    message = callback_query.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    user_id = callback_query.get("from", {}).get("id") or chat_id

    print(f"[*] Callback query '{data}' from {chat_id} (User: {user_id})", flush=True)
    answer_callback_query(cq_id)

    if data == "menu_main":
        send_message(chat_id, "🦅 <b>Dooro adeegga aad u baahan tahay:</b>", get_main_keyboard())
    elif data == "quiz_q1":
        handle_quiz_step1(chat_id)
    elif data.startswith("quiz_f_"):
        field = data.replace("quiz_f_", "")
        handle_quiz_step2(chat_id, field)
    elif data.startswith("quiz_l_"):
        parts = data.split("_")
        if len(parts) >= 4:
            handle_quiz_step3(chat_id, parts[2], parts[3])
    elif data.startswith("quiz_r_"):
        parts = data.split("_")
        if len(parts) >= 5:
            handle_quiz_result(chat_id, parts[2], parts[3], parts[4])
    elif data == "menu_jobs":
        handle_jobs(chat_id)
    elif data == "menu_cv":
        handle_cv(chat_id)
    elif data == "menu_tg_admin":
        handle_tg_admin(chat_id, user_id)
    elif data == "tg_groups":
        handle_tg_groups(chat_id)
    elif data == "tg_channels":
        handle_tg_channels(chat_id)
    elif data == "tg_referral":
        handle_tg_referral(chat_id, user_id)
    elif data == "tg_conflict":
        handle_tg_conflict(chat_id)
    elif data == "tg_docs":
        handle_tg_docs(chat_id)
    elif data == "tg_lesson_beg":
        handle_tg_lesson(chat_id, "beginner")
    elif data == "tg_lesson_int":
        handle_tg_lesson(chat_id, "intermediate")
    elif data == "tg_lesson_adv":
        handle_tg_lesson(chat_id, "advanced")
    elif data == "tg_lesson_it":
        handle_tg_lesson(chat_id, "it")
    elif data == "menu_academy":
        handle_academy(chat_id)
    elif data == "menu_booking":
        handle_booking(chat_id)
    elif data == "menu_contact":
        handle_contact(chat_id)
    elif data == "contact_ai_chat":
        text = """🤖 <b>Kaaliyaha AI waa diyaar!</b>

Qor su'aashaada adoo adeegsanaya qoraal toos ah (tusaale: <i>'Ii raadi shaqo maamul ama IT'</i> ama <i>'Sideen CV u qoraa?'</i>). Kaaliyaha AI ayaa isla markiiba kuugu soo jawaabaya! 🚀"""
        send_message(chat_id, text, {"inline_keyboard": [[{"text": "🔙 Ku noqo Xidhiidhka", "callback_data": "menu_contact"}]]})
    elif data == "menu_broadcast":
        handle_broadcast(chat_id)

def process_message(message):
    chat = message.get("chat", {})
    chat_id = chat.get("id")
    chat_type = chat.get("type", "private")
    is_group = chat_type in ["group", "supergroup"]
    text = message.get("text", "").strip()
    first_name = chat.get("first_name", "Walaal")
    user_id = message.get("from", {}).get("id") or chat_id

    # 1. Handle New Chat Members in Groups (Classroom Welcome)
    if "new_chat_members" in message:
        for member in message["new_chat_members"]:
            m_name = member.get("first_name", "Arday")
            if member.get("is_bot") and member.get("username") == "Baahiyebot":
                send_message(chat_id, "👋 <b>Salamaat Dhammaan!</b> Waxaan ahay Kaaliyaha AI ee fasalka / group-ka. Waxaan diyaar u ahay inaan idinka caawiyo ilaalinta anshaxa, soo dhoweynta ardayda cusub, iyo ka jawaabista su'aalaha casharrada. Qor <code>/ask [su'aashaada]</code>!")
            elif not member.get("is_bot"):
                welcome_group = f"""👋 <b>Ku soo dhowow fasalka, {m_name}!</b>

📖 Fadlan ilaali anshaxa iyo xeerarka fasalka:
1. Ka fogow xayeysiisyada spam-ka ah iyo links-ka aan la ogolayn.
2. Is-ixtiraama oo ka faa'iideysta casharrada.
3. Haddii aad qabto su'aal ku saabsan casharka, qor <code>/ask [su'aashaada]</code>."""
                send_message(chat_id, welcome_group)
        return

    # 2. Profanity & Spam Filter in Groups
    if is_group and text:
        text_check = text.lower()
        has_profanity = any(re.search(r"\b" + re.escape(v) + r"\b", text_check) for v in VULGAR_WORDS)
        has_invite_spam = ("t.me/joinchat" in text_check or "t.me/+" in text_check) and not any(w in text_check for w in ["baahiyebot", "isbar-ai.com"])
        if has_profanity or has_invite_spam:
            msg_id = message.get("message_id")
            if msg_id:
                delete_message(chat_id, msg_id)
            sender_name = message.get("from", {}).get("first_name", "Walaal")
            send_message(chat_id, f"⚠️ <b>Digniin:</b> {sender_name}, fariintaada waa la tirtiray sababtoo ah waxay jabisay xeerarka anshaxa fasalka/group-ka.")
            return

    # 3. AI Assistant in Groups:
    if is_group and text:
        if text.startswith("/ask") or text.startswith("/suaal") or "@baahiyebot" in text.lower():
            clean_q = text.replace("/ask", "").replace("/suaal", "").replace("@baahiyebot", "").replace("@Baahiyebot", "").strip()
            if clean_q:
                ai_ans = get_career_ai_response(clean_q)
                html_ans = ai_ans.replace("**", "<b>", 1)
                while "**" in html_ans:
                    html_ans = html_ans.replace("**", "</b>", 1)
                    html_ans = html_ans.replace("**", "<b>", 1)
                send_message(chat_id, f"💡 <b>Jawaabta Kaaliyaha AI:</b>\n\n{html_ans}")
            else:
                send_message(chat_id, "💡 Fadlan qor su'aashaada adoo adeegsanaya: <code>/ask [su'aashaada]</code>")
            return
        # Don't respond to general group chatter unless invoked
        return

    if not text:
        return

    print(f"[*] Incoming message from {chat_id} ({first_name}): {text}", flush=True)
    text_lower = text.lower()

    # Handle Referral & Start parameters
    if text_lower.startswith("/start"):
        parts = text.split()
        if len(parts) > 1:
            param = parts[1].strip()
            if param.startswith("ref_"):
                referrer = param.replace("ref_", "")
                if referrer.isdigit():
                    get_user_record(user_id, referrer_id=int(referrer))
                handle_start(chat_id, first_name)
                return
            elif param == "tg_admin":
                handle_tg_admin(chat_id, user_id)
                return
            elif param in ["group_admin", "groups"]:
                handle_tg_groups(chat_id)
                return
            elif param in ["channel_admin", "channels"]:
                handle_tg_channels(chat_id)
                return
            elif param in ["quiz", "quize"]:
                handle_quiz_step1(chat_id)
                return
            elif param == "ref":
                handle_tg_referral(chat_id, user_id)
                return
        get_user_record(user_id)
        handle_start(chat_id, first_name)
        return

    elif text_lower in ["start", "bilaaw", "menu", "hi", "halo", "sxb", "salaam", "asc"]:
        handle_start(chat_id, first_name)
    elif text_lower in ["/quiz", "quiz", "quize", "shaqo raadi", "ii raadi shaqo", "ii raadi", "dooro", "xirfad"]:
        handle_quiz_step1(chat_id)
    elif text_lower in ["/admin", "/tg_admin", "maamul", "maamulka", "telegram", "fasal", "channel"]:
        handle_tg_admin(chat_id, user_id)
    elif text_lower in ["/ref", "referral", "keen", "share", "40 cisho"]:
        handle_tg_referral(chat_id, user_id)
    elif text_lower in ["/english", "english", "ingiriis", "cashar", "lesson"]:
        handle_tg_channels(chat_id)
    elif text_lower in ["/jobs", "shaqo", "shaqooyin", "jobs"]:
        handle_jobs(chat_id)
    elif text_lower in ["/cv", "resume", "wareysi"]:
        handle_cv(chat_id)
    elif text_lower in ["/academy", "/books", "/courses", "buug", "koorso", "isbar", "buugaag", "buugag", "soo dir"]:
        handle_academy(chat_id)
    elif text_lower in ["/booking", "ballan", "mentorship"]:
        handle_booking(chat_id)
    elif text_lower in ["/contact", "/support", "/help", "contact", "contacts", "xiriir", "xidhiidh", "taageero", "support", "help", "caawinaad", "human", "qof", "mfaratoon", "faratoon", "substack"]:
        handle_contact(chat_id)
    elif text_lower in ["/broadcast", "baahin"]:
        handle_broadcast(chat_id)
    elif any(w in text_lower for w in ["sida loo", "sidee loo", "sameeyaa", "repo", "source code", "shubo", "deploy", "dhis", "github", "opensource"]):
        reply_repo = f"""⭐ <b>Madashan waa 100% Free & Open Source (U fasaxan qof kasta):</b>

Repository-ga rasmiga ah waa bilaash oo qof kasta wuu ka faa'iideysan karaa ama horumarin karaa:
🔗 <a href='{GITHUB_REPO_URL}'>GitHub Repository</a>

🚀 <b>Ma rabtaa inaad barato sida nidaamkan oo kale loogu shubo loona dhiso iyadoo AI la adeegsanayo?</b>
Qofkii raba inuu barto sida loo dhiso loona shubo codsiyada casriga ah ee AI-ga, waxaad dooran kartaa <b>'Ballan Qabso'</b> (Live 1-on-1 Mentorship oo toos ah oo aad la yeelanayso <b>Mohamed Yasin</b>)."""
        send_message(chat_id, reply_repo, {
            "inline_keyboard": [
                [{"text": "📅 Qabso Ballan Live ah", "callback_data": "menu_booking"}],
                [{"text": "⭐ Eeg GitHub Repo", "url": GITHUB_REPO_URL}],
                [{"text": "🔙 Ku noqo Menu-ga", "callback_data": "menu_main"}]
            ]
        })
    elif text_lower in ["/app", "miniapp", "app"]:
        send_message(chat_id, "🚀 <b>Guji badhanka hoose si aad u furto Web App-ka (isbar-ai.com):</b>", {
            "inline_keyboard": [
                [{"text": "📱 Fur isbar-ai.com", "web_app": {"url": WEB_APP_URL}}],
                [{"text": "🔙 Ku noqo Menu-ga", "callback_data": "menu_main"}]
            ]
        })
    else:
        # Check spam
        is_spam, reason = is_spam_or_invalid(text)
        if is_spam:
            send_message(chat_id, reason)
            return

        # AI Career response
        ai_reply = get_career_ai_response(text)
        html_reply = ai_reply.replace("**", "<b>", 1)
        while "**" in html_reply:
            html_reply = html_reply.replace("**", "</b>", 1)
            html_reply = html_reply.replace("**", "<b>", 1)

        markup = {
            "inline_keyboard": [
                [{"text": "📱 Fur isbar-ai.com", "web_app": {"url": WEB_APP_URL}}],
                [{"text": "💼 Fursadaha Shaqada", "callback_data": "menu_jobs"}, {"text": "🔙 Menu-ga", "callback_data": "menu_main"}]
            ]
        }
        send_message(chat_id, html_reply, markup, parse_mode="HTML")

def run_bot_polling():
    print("\n=======================================================", flush=True)
    print("   Shaqo Baahiye Telegram Bot (@Baahiyebot)", flush=True)
    print("   Bot: @Baahiyebot (Clean & Modernized)", flush=True)
    print(f"   Domain: {PRIMARY_DOMAIN}", flush=True)
    print("=======================================================\n", flush=True)

    configure_bot_menu_button()

    offset = None
    while True:
        try:
            url = f"{API_URL}/getUpdates"
            params = {"timeout": 30}
            if offset:
                params["offset"] = offset

            res = requests.get(url, params=params, timeout=40)
            if res.status_code == 200:
                data = res.json()
                if data.get("ok"):
                    for update in data.get("result", []):
                        offset = update.get("update_id") + 1
                        if "message" in update:
                            process_message(update["message"])
                        elif "callback_query" in update:
                            process_callback_query(update["callback_query"])
            else:
                print(f"[!] getUpdates response code {res.status_code}: {res.text}", flush=True)
                time.sleep(5)
        except requests.exceptions.RequestException:
            time.sleep(2)
        except Exception as e:
            print(f"[!] Unexpected error in bot loop: {e}", flush=True)
            time.sleep(2)

if __name__ == "__main__":
    run_bot_polling()
