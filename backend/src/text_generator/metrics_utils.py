from nltk.translate.bleu_score import sentence_bleu, SmoothingFunction
from rouge_score import rouge_scorer


def compute_bleu(reference: str, hypothesis: str) -> float:
    """
    Считает BLEU score между эталонным и сгенерированным текстом.
    reference — исходный шаблон (например, body_text из Templates)
    hypothesis — итоговое поздравление.
    """
    smoothie = SmoothingFunction().method1
    ref_tokens = reference.split()
    hyp_tokens = hypothesis.split()
    try:
        return round(sentence_bleu([ref_tokens], hyp_tokens, smoothing_function=smoothie), 4)
    except ZeroDivisionError:
        return 0.0


def compute_rouge(reference: str, hypothesis: str) -> dict:
    """
    Считает ROUGE-1, ROUGE-L.
    Возвращает словарь вроде {'rouge1': 0.73, 'rougeL': 0.65}
    """
    scorer = rouge_scorer.RougeScorer(['rouge1', 'rougeL'], use_stemmer=True)
    scores = scorer.score(reference, hypothesis)
    return {k: round(v.fmeasure, 4) for k, v in scores.items()}
