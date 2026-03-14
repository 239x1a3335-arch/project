import requests

API_KEY = "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"
URL = "https://openrouter.ai/api/v1/chat/completions"
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

def get_chat_response(prompt):
    data = {
        "model": "openai/gpt-4o",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1000
    }
    response = requests.post(URL, headers=HEADERS, json=data)
    if response.status_code == 200:
        result = response.json()
        return result["choices"][0]["message"]["content"]
    else:
        return f"Error: {response.status_code} - {response.text}"

if __name__ == "__main__":
    prompt = input("Enter your prompt: ")
    response = get_chat_response(prompt)
    print("Response:", response)