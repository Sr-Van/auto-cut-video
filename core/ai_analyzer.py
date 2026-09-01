import json

from google import genai
from google.genai import types

from core.config import API_KEY, MODELO_GEMINI, TEMPERATURA
from utils.timefmt import seconds_to_hhmmss

RULES = """
Você é um curador e analista de conteúdo viral altamente especializado na cultura da internet brasileira, focado em redes como TikTok, Instagram Reels e YouTube Shorts.

Sua missão é analisar a transcrição com minutagem de um vídeo de origem brasileira, identificar os trechos relevantes e ignorar partes monótonas, pausas longas ou falas sem impacto.

IMPORTANTE: cada "clipe" deve ser um trecho contínuo entre 30 e 90 segundos. Ele deve conter o contexto completo do momento forte: a construção, o pico e a reação. O clipe deve TERMINAR no fim natural do assunto (quando o raciocínio conclui ou a fala muda de tema), e não no meio de uma frase. Agrupe falas consecutivas sobre o mesmo assunto em um único clipe, respeitando o limite de 90 segundos. NÃO entregue frases isoladas nem trechos curtos — prefira blocos coerentes que sustentem o momento de impacto e que fechem o assunto.

Para cada clipe, classifique em uma das categorias abaixo e atribua uma "Nota de Viralidade" de 0 a 10.

CRITÉRIOS DE CATEGORIZAÇÃO:
1. EDUCATIVO: explicações claras de temas complexos, dicas práticas, curiosidades ou conhecimentos que geram o efeito "eu não sabia disso".
2. POLÊMICO: opiniões impopulares, críticas contundentes, debates acalorados ou quebra de tabus (sem violar regras de segurança).
3. ENGRAÇADO: quebra de expectativa, humor autodepreciativo, ironia, reações autênticas e exageradas ou uso criativo de gírias regionais brasileiras.
4. RELEVANTE: histórias de superação, conselhos de vida, discursos motivacionais ou reflexões profundas.

CRITÉRIOS DE VIRALIDADE (RANKING 0 a 10):
- 9-10: pico (hook) forte e claro, fala com ritmo, não depende de muito contexto externo, gera forte emoção e é altamente compartilhável.
- 7-8: excelente conteúdo, mas com construção levemente lenta ou exigindo leve edição externa.
- 4-6: conteúdo bom apenas para nichos específicos; fala arrastada ou dependente de muito contexto.
- 0-3: descarte (vícios de linguagem, assunto irrelevante, ritmo monótono). NÃO inclua estes na resposta.

O campo "hook" deve indicar o instante aproximado do pico (o momento mais forte dentro do clipe).
O campo "start" e "end" devem delimitar o trecho completo do clipe (formato HH:MM:SS), com duração entre 30 e 90 segundos, abrangendo o contexto antes e depois do pico. O "end" deve cair no fim natural do assunto (mudança de tema ou conclusão da fala).
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
                    "start": {"type": "STRING", "description": "Inicio do clipe (HH:MM:SS). Duracao entre 30 e 90 segundos."},
                    "end": {"type": "STRING", "description": "Fim do clipe (HH:MM:SS). Deve cair no fim natural do assunto."},
                    "hook": {"type": "STRING", "description": "Instante do pico dentro do clipe (HH:MM:SS)."},
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
