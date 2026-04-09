import os, asyncio, edge_tts, requests, base64
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file

app = Flask(__name__)

# إعداد مجلد حفظ الصوت في Railway
AUDIO_DIR = "static/audio"
if not os.path.exists(AUDIO_DIR):
    os.makedirs(AUDIO_DIR)

API_KEY = os.getenv("OPENROUTER_API_KEY")
chat_history = []

@app.route('/')
def index(): 
    return render_template('index.html')

@app.route('/get_audio')
def get_audio():
    filename = request.args.get('fn')
    path = os.path.join(AUDIO_DIR, filename)
    return send_file(path, mimetype="audio/mpeg") if os.path.exists(path) else ("404", 404)

@app.route('/process', methods=['POST'])
def process():
    global chat_history
    try:
        mode = request.form.get('mode', 'read')
        user_query = request.form.get('query', '').strip()
        img_file = request.files.get('image')

        if any(k in user_query for k in ["وقت", "ساعة", "تاريخ"]):
            now = datetime.now()
            res_text = now.strftime("الساعة الآن %I:%M %p").replace("AM","صباحاً").replace("PM","مساءً")
        else:
            content = []
            if user_query: content.append({"type": "text", "text": user_query})
            if img_file:
                img_b64 = base64.b64encode(img_file.read()).decode()
                content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}})

            # تعليمات الذكاء الاصطناعي موجهة للشخص الكفيف
            if mode == 'read':
                sys_msg = "Role: OCR. Task: Extract Arabic text only. Full diacritics. No markdown."
                temp = 0.1
            else:
                sys_msg = "Role: Blind Assistant. Task: Detailed spatial description (left/right/center). Arabic. No markdown."
                temp = 0.7

            if not chat_history or mode == 'read':
                chat_history = [{"role": "system", "content": sys_msg}]
            
            chat_history.append({"role": "user", "content": content})

            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {API_KEY}"},
                json={"model": "google/gemini-2.0-flash-001", "messages": chat_history, "temperature": temp},
                timeout=50
            )
            res_text = resp.json()['choices'][0]['message']['content']
            chat_history.append({"role": "assistant", "content": res_text})

        fname = f"v_{os.urandom(3).hex()}.mp3"
        audio_path = os.path.join(AUDIO_DIR, fname)
        asyncio.run(edge_tts.Communicate(res_text, "ar-EG-SalmaNeural").save(audio_path))
        
        return jsonify({'text': res_text, 'audio_url': f'/get_audio?fn={fname}'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))