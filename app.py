from flask import Flask, request, render_template, send_file
from datetime import datetime
import requests
import io
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
import json

app = Flask(__name__)

API_KEY = "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"
URL = "https://openrouter.ai/api/v1/chat/completions"
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

HISTORY_FILE = 'chat_history.json'
TESTS_FILE = 'tests.json'

def load_history():
    try:
        with open(HISTORY_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_history(history):
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history, f)

def load_tests():
    try:
        with open(TESTS_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_tests(tests):
    with open(TESTS_FILE, 'w') as f:
        json.dump(tests, f)

# Core OpenRouter/AI integration
def get_chat_response(prompt, system_instruction=None, max_tokens=1200):
    messages = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": prompt})

    data = {
        "model": "openai/gpt-4o",
        "messages": messages,
        "max_tokens": max_tokens
    }
    response = requests.post(URL, headers=HEADERS, json=data)
    if response.status_code == 200:
        result = response.json()
        return result["choices"][0]["message"]["content"]
    else:
        return f"Error: {response.status_code} - {response.text}"

def generate_mcq_test(syllabus, difficulty, count):
    system = (
        "You are an expert exam generator and learning coach. "
        "Generate high-quality multiple-choice questions based on the provided syllabus. "
        "You must respond ONLY with valid JSON (no extra text, no markdown, no explanation outside JSON)."
    )

    def build_prompt():
        return (
            f"Generate {count} multiple-choice questions (MCQs) based on the syllabus below. "
            f"Each question must include exactly 4 answer options and identify the correct answer. "
            f"For each question, provide a brief explanation (2-3 sentences) of why the answer is correct. "
            f"Return a valid JSON object with a single key named \"questions\". "
            f"Each question item must be an object with keys: \"question\", \"options\" (array of 4 strings), "
            f"\"answer\" (the full correct option text), and \"explanation\" (string). "
            f"Provide difficulty: {difficulty}.\n\n"
            f"Syllabus:\n{syllabus}\n\n"
            f"Example response format (use exact JSON format):\n"
            f"{{\n  \"questions\": [\n    {{\n      \"question\": \"...\",\n      \"options\": [\"A\", \"B\", \"C\", \"D\"],\n      \"answer\": \"A\",\n      \"explanation\": \"...\"\n    }}\n  ]\n}}\n"
        )

    def parse_json_response(text):
        try:
            parsed = json.loads(text)
            questions = parsed.get('questions')
            if isinstance(questions, list) and questions:
                # Ensure each question includes required fields
                clean = []
                for q in questions:
                    if not isinstance(q, dict):
                        continue
                    clean.append({
                        'question': str(q.get('question', '')).strip(),
                        'options': q.get('options') if isinstance(q.get('options'), list) else [],
                        'answer': str(q.get('answer', '')).strip(),
                        'explanation': str(q.get('explanation', '')).strip(),
                    })
                return clean
        except Exception:
            pass

        # Try to extract JSON object from text
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1 and end > start:
            snippet = text[start:end+1]
            try:
                parsed = json.loads(snippet)
                questions = parsed.get('questions')
                if isinstance(questions, list):
                    return questions
            except Exception:
                pass

        return None

    prompt = build_prompt()

    # Try 2 times to get valid JSON
    for attempt in range(2):
        response_text = get_chat_response(prompt, system_instruction=system, max_tokens=1600)
        questions = parse_json_response(response_text)
        if questions:
            return questions

        # If the first attempt failed, add guidance to respond only with JSON
        prompt += "\n\nPLEASE RESPOND WITH ONLY VALID JSON. DO NOT WRITE ANY EXTRA TEXT."

    # If parsing failed, return a fallback single question with clear guidance
    return [{
        'question': 'Unable to generate valid MCQs; please refine the syllabus and try again.',
        'options': ['--'],
        'answer': '--',
        'explanation': 'Edit the syllabus to be more specific and try again. If the problem persists, check your network or API key.'
    }]

@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json()
    prompt = data.get('prompt')
    if not prompt:
        return {'error': 'No prompt provided'}, 400
    response = get_chat_response(prompt)
    return {'response': response}

@app.route('/api/tests', methods=['GET', 'POST'])
def tests():
    if request.method == 'GET':
        return {'tests': load_tests()}

    data = request.get_json() or {}
    syllabus = data.get('syllabus', '').strip()
    difficulty = data.get('difficulty', 'medium')
    count = int(data.get('count', 10))
    subject = data.get('subject', '').strip()
    exam_date = data.get('examDate', '')
    duration = int(data.get('duration', 120))
    college_name = data.get('collegeName', '').strip()

    if not syllabus or not subject or not exam_date or not college_name:
        return {'error': 'All fields are required'}, 400

    questions = generate_mcq_test(syllabus, difficulty, count)
    if not questions:
        return {'error': 'Failed to generate questions'}, 500

    # Detect fallback placeholder response and surface as an error
    if len(questions) == 1 and isinstance(questions[0], dict) and questions[0].get('question', '').startswith('Unable to generate valid MCQs'):
        return {'error': questions[0].get('question')}, 500

    # Create 4 sets by shuffling questions
    import random
    sets = {}
    for set_name in ['A', 'B', 'C', 'D']:
        shuffled = questions.copy()
        random.shuffle(shuffled)
        sets[set_name] = shuffled

    tests = load_tests()
    test_id = str(int(datetime.now().timestamp() * 1000))
    new_test = {
        'id': test_id,
        'syllabus': syllabus,
        'difficulty': difficulty,
        'count': count,
        'subject': subject,
        'examDate': exam_date,
        'duration': duration,
        'collegeName': college_name,
        'questions': questions,  # original order
        'sets': sets,  # shuffled sets
        'createdAt': datetime.now().isoformat()
    }
    tests.append(new_test)
    save_tests(tests)
    return new_test

@app.route('/api/tests/<test_id>', methods=['GET'])
def get_test(test_id):
    tests = load_tests()
    for t in tests:
        if t.get('id') == test_id:
            return t
    return {'error': 'Test not found'}, 404

@app.route('/generate_pdf', methods=['POST'])
def generate_pdf():
    data = request.get_json() or {}
    history = data.get('history', [])
    test = data.get('test')
    pdf_type = data.get('type', 'question')  # 'question' or 'answer'
    set_name = data.get('set')  # 'A', 'B', 'C', 'D' or None for all

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    title_style = styles['Title']
    normal_style = styles['Normal']
    bold_style = styles['Heading2']

    elements = []

    if test:
        subject = test.get('subject', 'Subject')
        exam_date = test.get('examDate', 'Date')
        duration = test.get('duration', 120)
        college_name = test.get('collegeName', 'College Name')
        sets = test.get('sets', {})

        sets_to_generate = [set_name] if set_name else ['A', 'B', 'C', 'D']

        for idx, s_name in enumerate(sets_to_generate):
            if idx > 0:
                elements.append(Spacer(1, 24))  # Page break between sets
            questions = sets.get(s_name, [])

            if pdf_type == 'question':
                elements.append(Paragraph(f'Question Paper - Set {s_name}', title_style))
                elements.append(Spacer(1, 12))
                elements.append(Paragraph(f'Subject: {subject}', normal_style))
                elements.append(Paragraph(f'Exam Date: {exam_date}', normal_style))
                elements.append(Paragraph(f'Duration: {duration} minutes', normal_style))
                elements.append(Paragraph(f'College: {college_name}', normal_style))
                elements.append(Spacer(1, 12))
                elements.append(Paragraph('Roll No: ____________________', normal_style))
                elements.append(Paragraph('College Name: ____________________', normal_style))
                elements.append(Spacer(1, 12))

                for q_idx, q in enumerate(questions, start=1):
                    elements.append(Paragraph(f"<b>{q_idx}. {q.get('question')}</b>", bold_style))
                    options = q.get('options', [])
                    for opt_idx, option in enumerate(options, start=1):
                        elements.append(Paragraph(f"{chr(64+opt_idx)}. {option}", normal_style))
                    elements.append(Spacer(1, 6))
            else:
                elements.append(Paragraph(f'Answer Key - Set {s_name}', title_style))
                elements.append(Spacer(1, 12))
                elements.append(Paragraph(f'Subject: {subject}', normal_style))
                elements.append(Paragraph(f'Exam Date: {exam_date}', normal_style))
                elements.append(Paragraph(f'Duration: {duration} minutes', normal_style))
                elements.append(Paragraph(f'College: {college_name}', normal_style))
                elements.append(Spacer(1, 12))

                for q_idx, q in enumerate(questions, start=1):
                    elements.append(Paragraph(f"<b>{q_idx}. {q.get('question')}</b>", bold_style))
                    elements.append(Paragraph(f"Answer: {q.get('answer')}", normal_style))
                    elements.append(Spacer(1, 6))
    else:
        elements.append(Paragraph("Chat History", title_style))
        elements.append(Spacer(1, 12))

        for chat in history:
            elements.append(Paragraph(f"<b>Prompt:</b> {chat['prompt']}", bold_style))
            elements.append(Spacer(1, 6))
            elements.append(Paragraph(f"<b>Response:</b> {chat['response']}", normal_style))
            elements.append(Spacer(1, 6))
            elements.append(Paragraph(f"<i>Timestamp: {chat['timestamp']}</i>", normal_style))
            elements.append(Spacer(1, 12))

    doc.build(elements)
    buffer.seek(0)
    filename = f'ai_test_{pdf_type}_{set_name or "all"}.pdf' if test else 'chat_history.pdf'
    return send_file(buffer, as_attachment=True, download_name=filename, mimetype='application/pdf')

@app.route('/')
def index():
    return render_template('index.html')
import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
