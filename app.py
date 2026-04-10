import os, asyncio, edge_tts, requests, base64, re
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file

# --- إعداد التطبيق ---
app = Flask(__name__)

AUDIO_DIR = "/tmp"
os.makedirs(AUDIO_DIR, exist_ok=True)

API_KEY = os.getenv("OPENROUTER_API_KEY")
sessions = {}

def detect_language(text):
    arabic_chars = len(re.findall(r'[\u0600-\u06FF]', text))
    english_chars = len(re.findall(r'[a-zA-Z]', text))
    return 'ar' if arabic_chars >= english_chars else 'en'

async def generate_audio(text, filename):
    lang = detect_language(text)
    if lang == 'ar':
        voice = "ar-SA-ZariyahNeural"  # صوت عربي فصيح أكاديمي أنثوي هادئ
        rate = "-15%"
    else:
        voice = "en-US-AriaNeural"     # صوت إنجليزي أنثوي جميل وواضح
        rate = "-10%"
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    await communicate.save(filename)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_audio')
def get_audio():
    filename = request.args.get('fn')
    if not filename or '/' in filename or '..' in filename:
        return ("403", 403)
    path = os.path.join(AUDIO_DIR, filename)
    return send_file(path, mimetype="audio/mpeg") if os.path.exists(path) else ("404", 404)

@app.route('/process', methods=['POST'])
def process():
    try:
        mode = request.form.get('mode', 'read')
        user_query = request.form.get('query', '').strip()
        session_id = request.form.get('session_id', 'default')
        img_file = request.files.get('image')

        if any(k in user_query for k in ["وقت", "ساعة", "تاريخ"]):
            now = datetime.now()
            res_text = now.strftime("الساعة الآن %I:%M %p").replace("AM", "صباحاً").replace("PM", "مساءً")
        else:
            content = []
            if user_query:
                content.append({"type": "text", "text": user_query})
            if img_file:
                img_b64 = base64.b64encode(img_file.read()).decode()
                content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}})

            if mode == 'read':
                sys_msg = (
                    "Role: Professional OCR Assistant. "
                    "Task: Extract all readable text from the image exactly as written. "
                    "If the text is Arabic, output it with full diacritics (Tashkeel). "
                    "If the text is English, output it clearly as-is. "
                    "Constraint: Output ONLY the extracted text. "
                    "No introductions, no explanations, no markdown symbols."
                )
                temp = 0.1
            else:
                sys_msg = (
                    "Role: Expert Visual Assistant for the Blind. "
                    "Task: Describe the image comprehensively for someone who cannot see. "
                    "Language: Fluent, warm, and clear Arabic with no markdown. "
                    "Goal: Provide a full mental picture of the surroundings."
                )
                temp = 0.7

            if session_id not in sessions or mode == 'read':
                sessions[session_id] = [{"role": "system", "content": sys_msg}]

            sessions[session_id].append({"role": "user", "content": content})

            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {API_KEY}"},
                json={
                    "model": "google/gemini-2.0-flash-001",
                    "messages": sessions[session_id],
                    "temperature": temp
                },
                timeout=40
            )

            res_text = resp.json()['choices'][0]['message']['content']
            sessions[session_id].append({"role": "assistant", "content": res_text})

            if len(sessions[session_id]) > 20:
                sessions[session_id] = sessions[session_id][:1] + sessions[session_id][-10:]

        fname = f"v_{os.urandom(4).hex()}.mp3"
        audio_path = os.path.join(AUDIO_DIR, fname)
        asyncio.run(generate_audio(res_text, audio_path))

        return jsonify({'text': res_text, 'audio_url': f'/get_audio?fn={fname}'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
