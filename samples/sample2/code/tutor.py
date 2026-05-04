from openai import OpenAI


class AITutor:
    def __init__(self):
        self.client = OpenAI()

    def explain(self, topic: str, student_level: str) -> str:
        prompt = f"Explain {topic} for a {student_level} student in simple terms."
        response = self.client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content

    def generate_quiz(self, topic: str, num_questions: int = 5) -> list:
        prompt = f"Generate {num_questions} multiple choice questions about {topic}. Return as JSON array."
        response = self.client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
