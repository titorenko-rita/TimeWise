from datetime import datetime

class Message:
    """
    Заглушка под таблицу Messages.
    В будущем данные будут сохраняться в БД.
    """
    def __init__(self, template_id, contact_id, rendered_text):
        self.template_id = template_id
        self.contact_id = contact_id
        self.rendered_text = rendered_text
        self.pdf_path = None
        self.grammar_score = None
        self.toxicity_score = None
        self.approved_by = None
        self.approved_at = None
        self.created_at = datetime.now()

    def save(self):
        """
        Имитация сохранения сообщения в базу данных.
        Пока просто выводит данные в консоль.
        """
        print(f"\n💾 Сохранено сообщение:")
        print(f"Template ID: {self.template_id}")
        print(f"Contact ID: {self.contact_id}")
        print(f"Text: {self.rendered_text}")
        print(f"Дата: {self.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n")
