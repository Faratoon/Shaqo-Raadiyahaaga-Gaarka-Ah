import os
import sys
import time
import json
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

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or "8584246460:AAG_WjyrasBDU1mf959bh_TlzW1pIv1o48c"
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
PRIMARY_DOMAIN = "https://isbar-ai.com"
FALLBACK_DOMAIN = "https://auto-jobs-applier-aih-awk-live.vercel.app"
WEB_APP_URL = PRIMARY_DOMAIN
GITHUB_REPO_URL = "https://github.com/Faratoon/Shaqo-Raadiyahaaga-Gaarka-Ah"
SUBSTACK_URL = "https://somalilibrary.substack.com"
DHEGEYSO_BUUG_SUBSTACK = "https://dhegeysobuug.substack.com/"
YOUTUBE_URL = "https://www.youtube.com/@Mfaratoon"
SHARE_TEXT = urllib.parse.quote("🔥 Fursadaha Shaqo & Akadeemiyada Isbar (isbar-ai.com)! Ka faa'iideyso @Baahiyebot & Mini App-ka 🚀")

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

def get_main_keyboard():
    return {
        "inline_keyboard": [
            # Row 1: Full-width Web App button
            [
                {"text": "🚀 Fur Web App-ka (isbar-ai.com)", "web_app": {"url": WEB_APP_URL}}
            ],
            # Row 2: 2-column Career & CV Actions
            [
                {"text": "💼 Fursadaha Shaqada 🔥", "callback_data": "menu_jobs"},
                {"text": "⚡ Dhis CV (ATS)", "callback_data": "menu_cv"}
            ],
            # Row 3: 2-column Learning & Mentorship
            [
                {"text": "📚 Buugaagta Isbar", "callback_data": "menu_academy"},
                {"text": "📅 Ballan Live ah", "callback_data": "menu_booking"}
            ],
            # Row 4: 2-column Public Info & Community
            [
                {"text": "📬 Xidhiidhka & Substack", "callback_data": "menu_contact"},
                {"text": "📢 Baahi / Share", "callback_data": "menu_broadcast"}
            ],
            # Row 5: Open Source GitHub Showcase
            [
                {"text": "⭐ GitHub (100% Open Source)", "url": GITHUB_REPO_URL}
            ]
        ]
    }

def handle_start(chat_id, first_name):
    welcome_text = f"""🦅 <b>Shaqo Baahiye (@Baahiyebot)</b>

Ku soo dhowow <b>{first_name}</b>! Madal u heellan fursadaha shaqada oo dhan, iyadoo ahmiyad gaar ah iyo showcase siinaysa dhalinyarada bartay IT-ga & CS-ka, diyaarinta CV ATS ah, iyo buugaagta casriga ah ee Isbar.

<i>Dooro adeegga aad u baahan tahay hoos:</i>"""

    banner_path = BASE_DIR / "assets" / "shaqo_baahiye_banner.png"
    if banner_path.exists():
        send_photo(chat_id, banner_path, caption=welcome_text, reply_markup=get_main_keyboard())
    else:
        send_message(chat_id, welcome_text, get_main_keyboard())

def handle_jobs(chat_id):
    jobs = get_curated_somali_it_jobs()
    text = """💼 <b>Fursadaha Shaqada (All Careers & IT Showcase):</b>

Nidaamku wuxuu kuu raadinayaa dhammaan noocyada shaqooyinka (IT Support, Software, Data, Customer Care, Management) ee Soomaaliya (Muqdisho & Hargeysa), Bariga Afrika (Kenya, Itoobiya), Shaqooyinka Guriga (Global Remote), iyo Kanada.

<b>Fursadaha Ugu Dambeeyay ee Tooska ah:</b>\n\n"""
    
    for idx, j in enumerate(jobs[:4], 1):
        text += f"<b>{idx}. {j['title']}</b>\n"
        text += f"🏢 {j['company']} &bull; 📍 {j['location']}\n"
        text += f"🔗 <a href='{j['job_url']}'>Codsashada Tooska ah</a>\n\n"

    markup = {
        "inline_keyboard": [
            [{"text": "📱 Baadh Dhammaan Shaqooyinka (Web App)", "web_app": {"url": f"{WEB_APP_URL}#jobsSection"}}],
            [
                {"text": "🇸🇴 Soomaaliya & Bariga Afrika", "web_app": {"url": f"{WEB_APP_URL}#jobsSection"}},
                {"text": "🌐 Remote & Canada", "web_app": {"url": f"{WEB_APP_URL}#jobsSection"}}
            ],
            [{"text": "📤 Share garee Shaqooyinka", "url": f"https://t.me/share/url?url=https://t.me/Baahiyebot&text={SHARE_TEXT}"}],
            [{"text": "🔙 Ku noqo Menu-ga", "callback_data": "menu_main"}]
        ]
    }
    send_message(chat_id, text, markup)

def handle_cv(chat_id):
    text = """⚡ <b>Diyaarinta CV ATS ah & Diyaar-garowga Wareysiga:</b>

• 📄 <b>ATS Resume (1-Page):</b> Qaab nadiif ah oo shirkadaha caalamiga ah iyo kuwa maxalliga ah u aqbalaan si toos ah iyadoo nidaamyada casriga ahi aysan reebayn.
• 📝 <b>Cover Letter:</b> Warqad codsi oo ku habboon doorka aad codsanayso.
• 🎯 <b>STAR Method:</b> Qaabka ugu guulaha badan ee looga jawaabo wareysiyada (Situation, Task, Action, Result).

<i>Ka soo degso resume-ga rasmiga ah ama AI-ga ku falanqee xirfadahaaga:</i>"""

    markup = {
        "inline_keyboard": [
            [{"text": "⚡ Dhis & Falanqee CV-gaaga (Web App)", "web_app": {"url": f"{WEB_APP_URL}#assessSection"}}],
            [{"text": "📄 Soo Degso Resume Template (PDF)", "url": f"{WEB_APP_URL}/download/resume"}],
            [{"text": "🔙 Ku noqo Menu-ga", "callback_data": "menu_main"}]
        ]
    }
    send_message(chat_id, text, markup)

def handle_academy(chat_id):
    text = """📚 <b>Akadeemiyada Isbar & Koorsooyinka Bilaashka ah:</b>

📖 <b>Buugaagta Isbar (Af-Soomaali):</b>
• 💻 <b>ISBAR COMPUTER</b> ($5) — 89 Pages (Windows 11, Mac OS, Office, Photoshop)
• 👨‍💻 <b>ISBAR PROGRAMMING</b> ($5) — 177 Pages (Web, Python, Database, IDEs)
• 🧠 <b>ISBAR AI BASIC</b> ($7) — 189 Pages (Taariikhda AI, Shaqooyinka, Ganacsiga)
• 🤖 <b>ISBAR ChatGPT Prompts</b> — 🎁 <b>Bilaash</b> (87 Pages)

📬 <b>Sidee ku helaysaa Buugaagta?</b>
Qof kasta oo ku biira (subscribe gareeya) warsidaha <b>Dhegeyso Buug</b> waxaan si toos ah emailkiisa ugu diraynaa buugaagta:
👉 <a href="https://dhegeysobuug.substack.com/">dhegeysobuug.substack.com</a>

🎓 <b>Koorsooyinka AI Automation (100% Bilaash):</b>
• 🎥 AI Video Editing &bull; 📱 WhatsApp & Telegram Business Bots
• 🌐 Web Design with AI Tools (HTML/CSS)"""

    markup = {
        "inline_keyboard": [
            [{"text": "📬 Ku Biir Dhegeyso Buug (Hel Buug)", "url": DHEGEYSO_BUUG_SUBSTACK}],
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

Kulan toos ah oo online ah (Google Meet / Zoom) oo aad la yeelanayso <b>Mohamed Yasin</b>:
• ✅ La-talin ku saabsan jihadaada shaqo iyo xirfadeed
• ✅ Dib-u-eegista CV-gaaga & Tababarka Wareysiga
• ✅ Hagidda helitaanka shaqooyinka & Koorsooyinka AI Automation

📍 <b>Edmonton, AB, Canada 🇨🇦 & Online Global</b>"""

    markup = {
        "inline_keyboard": [
            [{"text": "📅 Qabso Ballan Live ah (Web App)", "web_app": {"url": f"{WEB_APP_URL}#bookingSection"}}],
            [{"text": "💬 WhatsApp Toos ah (+1 587-306-4137)", "url": "https://wa.me/15873064137?text=Salamaat%20Mohamed,%20waxaan%20rabaa%20ballan%20live%20ah"}],
            [{"text": "🔙 Ku noqo Menu-ga", "callback_data": "menu_main"}]
        ]
    }
    send_message(chat_id, text, markup)

def handle_contact(chat_id):
    text = """📬 <b>Xidhiidhka & Xogta Dadweynaha (Public Contact & Info):</b>

Kala xidhiidh aasaasaha iyo kooxda nidaamka siyaabaha rasmiga ah:

• 📬 <b>Dhegeyso Buug Substack (Helitaanka Buugaagta):</b>
  <a href='https://dhegeysobuug.substack.com/'>dhegeysobuug.substack.com</a>

• 📬 <b>Somalilibrary Substack (Warsidaha Rasmiga ah):</b>
  <a href='https://somalilibrary.substack.com'>somalilibrary.substack.com</a>

• 📱 <b>WhatsApp Toos ah:</b> <a href='https://wa.me/15873064137'>+1 (587) 306-4137</a>
• 📧 <b>Email:</b> Suxufi34@gmail.com
• 🔗 <b>LinkedIn:</b> <a href='https://www.linkedin.com/in/mfaratoon'>linkedin.com/in/mfaratoon</a>
• 📺 <b>YouTube Portfolio:</b> <a href='https://www.youtube.com/@Mfaratoon'>youtube.com/@Mfaratoon</a>
• 🌐 <b>Website:</b> <a href='https://isbar-ai.com'>https://isbar-ai.com</a>

📍 <b>Mohamed Yasin</b> &bull; Edmonton, AB, Canada 🇨🇦"""

    markup = {
        "inline_keyboard": [
            [
                {"text": "📬 Dhegeyso Buug (Substack)", "url": DHEGEYSO_BUUG_SUBSTACK},
                {"text": "📬 Somalilibrary Substack", "url": SUBSTACK_URL}
            ],
            [
                {"text": "📱 WhatsApp Toos ah", "url": "https://wa.me/15873064137?text=Salamaat%20Mohamed,%20waxaan%20doonayaa%20macluumaad"},
                {"text": "🔗 LinkedIn", "url": "https://www.linkedin.com/in/mfaratoon"}
            ],
            [
                {"text": "📺 YouTube (@Mfaratoon)", "url": YOUTUBE_URL},
                {"text": "🌐 isbar-ai.com", "url": PRIMARY_DOMAIN}
            ],
            [{"text": "🔙 Ku noqo Menu-ga", "callback_data": "menu_main"}]
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

    print(f"[*] Callback query '{data}' from {chat_id}", flush=True)
    answer_callback_query(cq_id)

    if data == "menu_main":
        send_message(chat_id, "🦅 <b>Dooro adeegga aad u baahan tahay:</b>", get_main_keyboard())
    elif data == "menu_jobs":
        handle_jobs(chat_id)
    elif data == "menu_cv":
        handle_cv(chat_id)
    elif data == "menu_academy":
        handle_academy(chat_id)
    elif data == "menu_booking":
        handle_booking(chat_id)
    elif data == "menu_contact":
        handle_contact(chat_id)
    elif data == "menu_broadcast":
        handle_broadcast(chat_id)

def process_message(message):
    chat = message.get("chat", {})
    chat_id = chat.get("id")
    text = message.get("text", "").strip()
    first_name = chat.get("first_name", "Walaal")

    if not text:
        return

    print(f"[*] Incoming message from {chat_id} ({first_name}): {text}", flush=True)
    text_lower = text.lower()

    if text_lower in ["/start", "start", "bilaaw", "menu", "hi", "halo", "sxb", "salaam", "asc"]:
        handle_start(chat_id, first_name)
    elif text_lower in ["/jobs", "shaqo", "shaqooyin", "jobs"]:
        handle_jobs(chat_id)
    elif text_lower in ["/cv", "resume", "wareysi"]:
        handle_cv(chat_id)
    elif text_lower in ["/academy", "/books", "/courses", "buug", "koorso", "isbar", "buugaag", "buugag", "soo dir"]:
        handle_academy(chat_id)
    elif text_lower in ["/booking", "ballan", "mentorship"]:
        handle_booking(chat_id)
    elif text_lower in ["/contact", "/substack", "contact", "contacts", "xiriir", "xidhiidh", "substack"]:
        handle_contact(chat_id)
    elif text_lower in ["/broadcast", "/share", "baahin"]:
        handle_broadcast(chat_id)
    elif any(w in text_lower for w in ["sida loo", "sidee loo", "sameeyaa", "repo", "source code", "shubo", "deploy", "dhis", "github", "opensource"]):
        reply_repo = f"""⭐ <b>Madashan waa 100% Open Source (Bilaash):</b>

Repository-ga rasmiga ah waa bilaash oo qof kasta wuu ka faa'iideysan karaa:
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
