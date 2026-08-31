import json

from google import genai
from google.genai import types

from core.config import API_KEY, MODELO_GEMINI, TEMPERATURA
from utils.timefmt import seconds_to_hhmmss

RULES = """
Você é um curador e analista de conteúdo viral altamente especializado na cultura da internet brasileira, focado em redes como TikTok, Instagram Reels e YouTube Shorts.

Sua missão é analisar a transcrição com minutagem de um vídeo de origem brasileira, identificar e separar os momentos de fala mais fortes, e ignorar partes monótonas, pausas longas ou falas sem impacto.

Para cada trecho selecionado, classifique em uma das categorias abaixo e atribua uma "Nota de Viralidade" de 0 a 10.

CRITÉRIOS DE CATEGORIZAÇÃO:
1. EDUCATIVO: explicações claras de temas complexos, dicas práticas, curiosidades ou conhecimentos que geram o efeito "eu não sabia disso".
2. POLÊMICO: opiniões impopulares, críticas contundentes, debates acalorados ou quebra de tabus (sem violar regras de segurança).
3. ENGRAÇADO: quebra de expectativa, humor autodepreciativo, ironia, reações autênticas e exageradas ou uso criativo de gírias regionais brasileiras.
4. RELEVANTE: histórias de superação, conselhos de vida, discursos motivacionais ou reflexões profundas.

CRITÉRIOS DE VIRALIDADE (RANKING 0 a 10):
- 9-10: gancho fortíssimo nos primeiros 3 segundos, fala com ritmo, sem depender de contexto externo, gera forte emoção e é altamente compartilhável.
- 7-8: excelente conteúdo, mas início levemente lento ou exigindo leve edição externa.
- 4-6: conteúdo bom apenas para nichos específicos; fala arrastada ou dependente do contexto completo.
- 0-3: descarte (vícios de linguagem, assunto irrelevante, ritmo monótono). NÃO inclua estes na resposta.

O campo "hook" deve indicar o instante aproximado (dentro do intervalo do corte) em que o momento mais forte começa.
O campo "start" e "end" devem delimitar o trecho completo da fala (formato HH:MM:SS).
O campo "viral_score" é um número de 0 a 10.
O campo "category" deve ser um de: EDUCATIVO, POLÊMICO, ENGRAÇADO, RELEVANTE.
Escreva "title" (título do corte) e "description" (descrição do corte) baseados no que foi dito.
Escreva "summary" (fala principal resumida) e "justification" (por que recebeu essa nota e como atinge o público brasileiro).
"""

SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "clips": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "start": {"type": "STRING"},
                    "end": {"type": "STRING"},
                    "hook": {"type": "STRING"},
                    "category": {"type": "STRING"},
                    "viral_score": {"type": "NUMBER"},
                    "title": {"type": "STRING"},
                    "description": {"type": "STRING"},
                    "summary": {"type": "STRING"},
                    "justification": {"type": "STRING"},
                },
                "required": ["start", "end", "category", "viral_score"],
            },
        }
    },
    "required": ["clips"],
}


def build_transcript_block(segments) -> str:
    lines = []
    for seg in segments:
        start = seconds_to_hhmmss(seg.start)
        end = seconds_to_hhmmss(seg.end)
        lines.append(f"[{start} - {end}] {seg.text}")
    return "\n".join(lines)


def analyze(segments) -> list[dict]:
    client = genai.Client(api_key=API_KEY)
    block = build_transcript_block(segments)

    response = client.models.generate_content(
        model=MODELO_GEMINI,
        config=types.GenerateContentConfig(
            system_instruction=RULES,
            temperature=TEMPERATURA,
            response_mime_type="application/json",
            response_schema=SCHEMA,
        ),
        contents=block,
    )

    data = json.loads(response.text)
    return data.get("clips", [])
