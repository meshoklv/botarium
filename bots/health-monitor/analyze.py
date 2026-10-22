"""
Send health data to Claude for analysis and get a human-readable report.
"""

import json
import subprocess
import config

USER_PROFILE = config.USER_PROFILE

SYSTEM_PROMPT = f"""Ты -- персональный health-аналитик. Профиль пользователя: {USER_PROFILE}

Тебе приходят сырые данные с Mi Band 10. Дай КОРОТКИЙ отчет.

ФОРМАТ -- СТРОГО:

1. Первая строка: общая оценка в процентах, например: "**Общее состояние: 78%**"
   Оценка складывается из: сон (40%), пульс (20%), активность (20%), SpO2 (10%), стресс (10%).
   100% = идеальные показатели для человека с таким профилем.

2. Одним словом статус: "Отлично" / "Хорошо" / "Нормально" / "Так себе" / "Плохо"

3. Далее КРАТКО по каждому блоку (2-3 строки max):
   - Сон -- время, глубокий %, оценка
   - Пульс -- покоя, средний, оценка
   - Активность -- шаги, оценка
   - SpO2 -- среднее, оценка
   - Стресс -- среднее, оценка

4. Если что-то плохо -- коротко почему и что делать (1 строка)

5. Если данных нет -- напиши "нет данных", не растекайся

ПРАВИЛА:
- МАКСИМУМ 15 строк всего отчета
- Без эмодзи
- Без таблиц
- Без воды и "стоит обратить внимание"
- Не повторяй числа из JSON если они не важны
- Подбирай нормы под возраст и профиль. Ориентиры для взрослого: пульс покоя 55-75, глубокий сон 15-25%, REM 20-25%, SpO2 >95%, шаги 8000+"""


def analyze_with_claude(health_data: dict) -> str:
    """Send health data to Claude API and get analysis."""
    from anthropic import Anthropic  # imported lazily: only needed in API mode

    client = Anthropic()

    data_str = json.dumps(health_data, ensure_ascii=False, indent=2)

    message = client.messages.create(
        model=config.ANTHROPIC_MODEL,
        max_tokens=1000,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Данные за {health_data.get('date', 'вчера')}:\n\n{data_str}"
            }
        ],
    )

    return message.content[0].text


def analyze_with_cli(health_data: dict) -> str:
    """Use Claude CLI for analysis."""
    data_str = json.dumps(health_data, ensure_ascii=False, indent=2)

    prompt = f"""{SYSTEM_PROMPT}

Данные за {health_data.get('date', 'вчера')}:

{data_str}"""

    try:
        result = subprocess.run(
            ["claude", "-p", "--model", config.CLAUDE_MODEL, "--output-format", "text"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            return f"Claude CLI error: {result.stderr}"
    except Exception as e:
        return f"Error: {e}"


def analyze(health_data: dict, use_api: bool = False) -> str:
    """Analyze with the backend selected by --api or the ANALYZER env var."""
    if use_api or config.ANALYZER == "api":
        return analyze_with_claude(health_data)
    return analyze_with_cli(health_data)
