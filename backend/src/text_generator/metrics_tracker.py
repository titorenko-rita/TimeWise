import json
import os
from datetime import datetime
from collections import defaultdict


class MetricsTracker:
    def __init__(self, path=None):
        # по умолчанию — файл в корне проекта
        self.path = path or os.path.join(os.getcwd(), "metrics.json")
        # структура: { template_id: { "usage_count": int, "total_length": int, "avg_length": float, "last_used_at": str, "records": [ ... ] } }
        self.data = defaultdict(lambda: {
            "usage_count": 0,
            "total_length": 0,
            "avg_length": 0.0,
            "last_used_at": None,
            "records": []  # по желанию хранит свежие записи
        })
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                    # приводим ключи к строкам
                    for k, v in raw.items():
                        self.data[str(k)] = v
            except Exception:
                # если файл повреждён — начинаем заново
                self.data = defaultdict(lambda: {
                    "usage_count": 0,
                    "total_length": 0,
                    "avg_length": 0.0,
                    "last_used_at": None,
                    "records": []
                })

    def _save(self):
        # сохраняем словарь (приводим defaultdict к обычному dict)
        out = {k: v for k, v in self.data.items()}
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f"✅ Метрики сохранены в {self.path}")

    def update(self, template_id, text, contact_id=None, version=None, bleu=None, rouge=None):
        """
        Обновляет метрики для шаблона template_id.
        text — итоговый отрендеренный текст.
        contact_id, version — опционально для записи в records.
        bleu/rouge — опциональные числовые метрики.
        """
        tid = str(template_id)
        rec = self.data.get(tid, {
            "usage_count": 0,
            "total_length": 0,
            "avg_length": 0.0,
            "last_used_at": None,
            "records": []
        })

        rec["usage_count"] = rec.get("usage_count", 0) + 1
        rec["total_length"] = rec.get("total_length", 0) + len(text)
        rec["avg_length"] = rec["total_length"] / rec["usage_count"] if rec["usage_count"] else 0.0
        rec["last_used_at"] = datetime.utcnow().isoformat() + "Z"

        # короткая запись истории (последние N)
        record = {
            "ts": rec["last_used_at"],
            "contact_id": contact_id,
            "version": version,
            "length": len(text),
            "bleu": bleu,
            "rouge": rouge
        }
        records = rec.get("records", [])
        records.append(record)
        # держим не более 200 записей, чтобы файл не разрастался
        rec["records"] = records[-200:]

        self.data[tid] = rec
        self._save()
        print(f"📊 Обновляю метрики для шаблона {template_id}")

    def export_all(self):
        """Возвращает данные для отдачи по HTTP."""
        return {k: v for k, v in self.data.items()}
