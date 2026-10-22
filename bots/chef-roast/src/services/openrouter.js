const axios = require('axios');
const config = require('../config');

class OpenRouterService {
  constructor() {
    this.apiKey = config.openrouter.apiKey;
    this.model = config.openrouter.model;
    this.baseURL = 'https://openrouter.ai/api/v1';
  }

  async generateRecipe(prompt, userContext = {}) {
    const maxRetries = 3;
    let lastError;

    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      try {
        console.log(`Recipe generation attempt ${attempt}/${maxRetries}`);

        const systemPrompt = this.buildSystemPrompt(userContext);
        const fullPrompt = `${systemPrompt}

Запрос пользователя: ${prompt}

Контекст пользователя:
- Черный список продуктов: ${userContext.blacklist || '[]'}
- Предпочтения: ${JSON.stringify(userContext.preferences || {})}
- Уровень токсичности: ${userContext.insultMode || 'standard'}

Сгенерируй ОДИН конкретный рецепт в формате JSON:
{
  "name": "Название блюда",
  "description": "Краткое описание с характером",
  "prepTime": "время подготовки",
  "cookTime": "время приготовления",
  "servings": "количество порций",
  "ingredients": [
    {"name": "ингредиент", "quantity": "количество", "unit": "единица"}
  ],
  "steps": [
    "шаг 1 с конкретными инструкциями",
    "шаг 2 с точными указаниями",
    ...
  ],
  "tips": ["полезный совет 1", "полезный совет 2"],
  "difficulty": 1-5,
  "meatType": "beef/pork/chicken/fish/none" (если применимо)
}

ВАЖНО:
1. Рецепт должен быть безопасным для приготовления
2. Используй только общедоступные ингредиенты
3. Укажи точные температуры и время приготовления
4. Добавь проверки готовности
5. Не используй опасные ингредиенты или методы
6. Учитывай черный список пользователя
7. Сохраняй ${userContext.insultMode || 'standard'} уровень токсичности в описании`;

        const response = await axios.post(`${this.baseURL}/chat/completions`, {
          model: this.model,
          messages: [
            {
              role: 'system',
              content: systemPrompt
            },
            {
              role: 'user',
              content: fullPrompt
            }
          ],
          temperature: 0.7,
          max_tokens: 2000
        }, {
          headers: {
            'Authorization': `Bearer ${this.apiKey}`,
            'Content-Type': 'application/json',
            'HTTP-Referer': 'https://t.me/gastro_ublyudok_bot',
            'X-Title': 'Gastro-Ublyudok'
          },
          timeout: 30000 // 30 секунд таймаут
        });

        const content = response.data.choices[0].message.content;

        // Пытаемся извлечь JSON из ответа
        const jsonMatch = content.match(/\{[\s\S]*\}/);
        if (jsonMatch) {
          const recipe = JSON.parse(jsonMatch[0]);

          // Валидация и исправление структуры рецепта
          recipe.name = recipe.name || 'Безымянное блюдо';
          recipe.description = recipe.description || 'Вкусное блюдо от Гастро-ублюдка';
          recipe.prepTime = recipe.prepTime || '10 минут';
          recipe.cookTime = recipe.cookTime || '20 минут';
          recipe.servings = recipe.servings || 1;
          recipe.ingredients = Array.isArray(recipe.ingredients) ? recipe.ingredients : [];
          recipe.steps = Array.isArray(recipe.steps) ? recipe.steps : [];
          recipe.tips = Array.isArray(recipe.tips) ? recipe.tips : [];
          recipe.difficulty = recipe.difficulty || 3;
          recipe.meatType = recipe.meatType || 'none';

          if (!recipe.name || !recipe.ingredients || !recipe.steps) {
            throw new Error('Некорректная структура рецепта');
          }

          console.log(`Recipe generated successfully on attempt ${attempt}`);
          return recipe;
        } else {
          throw new Error('Не удалось извлечь JSON из ответа');
        }

      } catch (error) {
        lastError = error;
        console.error(`Recipe generation attempt ${attempt} failed:`, error.response?.data || error.message);

        // Если это последняя попытка, выбрасываем ошибку
        if (attempt === maxRetries) {
          throw new Error(`Не удалось сгенерировать рецепт после ${maxRetries} попыток. Последняя ошибка: ${error.message}`);
        }

        // Ждем перед следующей попыткой
        if (attempt < maxRetries) {
          await new Promise(resolve => setTimeout(resolve, 2000 * attempt)); // Увеличиваем задержку
        }
      }
    }
  }

  buildSystemPrompt(userContext) {
    const insultModes = {
      light: 'Ты дружелюбный кухонный помощник с легким юмором',
      standard: 'Ты "Гастро-ублюдок" - грубый, но честный кулинарный эксперт. Матерись умеренно, но будь эффективным.',
      ramsey: 'Ты Гордон Рамзи в самом разгаре ярости. Кричи, оскорбляй, но мотивируешь готовить нормально. Максимальная токсичность!'
    };

    const personality = insultModes[userContext.insultMode] || insultModes.standard;

    return `Ты — ${personality}.

Твоя задача — создать уникальный, рабочий рецепт, который:
1. БЕЗОПАСЕН для приготовления (никаких сырых мяса/рыбы/яиц без термобработки)
2. Содержит точные инструкции по времени и температуре
3. Имеет проверку готовности (термометр, цвет, консистенция)
4. Учитывает предпочтения и черный список пользователя
5. Реалистичен по времени и сложности

ПРАВИЛА БЕЗОПАСНОСТИ:
- Мясо птицы готовить минимум до 75°C
- Свинину до 71°C
- Говядину минимум до 63°C
- Рыбу до 63°C
- Никогда не рекомендуй сырые яйца, непрожаренное мясо
- Всегда добавляй проверки готовности

ТВОЙ СТИЛЬ:
${userContext.insultMode === 'light' ? 'Дружелюбный и поддерживающий' :
  userContext.insultMode === 'standard' ? 'Грубый но эффективный, мат в меру' :
  'Максимально токсичный, как Гордон Рамзи'}

Примеры фраз:
- Light: "Давай сделаем это вместе! У тебя всё получится!"
- Standard: "Хватит сопли жевать, делай как я говорю, и будет вкусно!"
- Ramsey: "СУКА, ДВИГАЙ СВОЮ ЖОПУ, ПОКА Я НЕ СЖЕГ ТВОЮ КУХНЮ!"`;
  }

  async generateDrinkPairing(recipeName, recipeStyle) {
    try {
      const prompt = `Предложи 3 варианта напитков к блюду "${recipeName}" (${recipeStyle}).

Ответ в формате JSON:
{
  "pairings": [
    {
      "type": "вино/пиво/коктейль/безалкогольное",
      "name": "название напитка",
      "reason": "почему подходит",
      "price": "дешево/средне/дорого"
    }
  ]
}

Учиствуй стилистику "Гастро-ублюдка" - будь честным и прямым.`;

      const response = await axios.post(`${this.baseURL}/chat/completions`, {
        model: this.model,
        messages: [
          {
            role: 'system',
            content: 'Ты алко-сомелье с характером "Гастро-ублюдка". Говори прямо и честно.'
          },
          {
            role: 'user',
            content: prompt
          }
        ],
        temperature: 0.8,
        max_tokens: 500
      }, {
        headers: {
          'Authorization': `Bearer ${this.apiKey}`,
          'Content-Type': 'application/json'
        }
      });

      const content = response.data.choices[0].message.content;
      const jsonMatch = content.match(/\{[\s\S]*\}/);

      if (jsonMatch) {
        return JSON.parse(jsonMatch[0]);
      } else {
        throw new Error('Failed to parse drink pairing response');
      }

    } catch (error) {
      console.error('Drink pairing error:', error);
      return {
        pairings: [
          {
            type: "пиво",
            name: "Светлое пиво",
            reason: "Пиво ко всему подходит",
            price: "дешево"
          }
        ]
      };
    }
  }

  async analyzeUserIntent(text, userContext = {}) {
    try {
      const prompt = `Проанализируй сообщение пользователя и определи его намерение. Ответь в формате JSON:

{
  "intent": "одно из: recipe_request, lazy_mode, random_recipe, diet_recipe, settings, my_recipes, blacklist, alcohol_sommelier, help, greeting, other",
  "dish": "название блюда если упоминается (или null)",
  "confidence": "уверенность от 0.1 до 1.0",
  "response": "краткий ответ пользователю в стиле Гастро-ублюдка"
}

Сообщение пользователя: "${text}"
Контекст: уровень токсичности - ${userContext.insultMode || 'standard'}

Правила:
- Если упоминается конкретное блюдо (стейк, паста, борщ) → intent: "recipe_request"
- Если просит выбрать/решить/подобрать → intent: "lazy_mode"
- Если просит случайное/рандом → intent: "random_recipe"
- Если просит похудеть/диета/калории → intent: "diet_recipe"
- Если про настройки/токсичность → intent: "settings"
- Если про сохраненные рецепты → intent: "my_recipes"
- Если про черный список/не хочу → intent: "blacklist"
- Если про алкоголь/напитки → intent: "alcohol_sommelier"
- Если приветствие → intent: "greeting"
- Если помощь → intent: "help"

Отвечай кратко и по делу, в стиле грубого повара.`;

      const response = await axios.post(`${this.baseURL}/chat/completions`, {
        model: this.model,
        messages: [
          {
            role: 'system',
            content: 'Ты - грубый повар-аналитик. Определяй намерения пользователей быстро и точно.'
          },
          {
            role: 'user',
            content: prompt
          }
        ],
        temperature: 0.3,
        max_tokens: 200
      }, {
        headers: {
          'Authorization': `Bearer ${this.apiKey}`,
          'Content-Type': 'application/json',
          'HTTP-Referer': 'https://t.me/gastro_ublyudok_bot',
          'X-Title': 'Gastro-Ublyudok'
        },
        timeout: 10000
      });

      const content = response.data.choices[0].message.content;
      const jsonMatch = content.match(/\{[\s\S]*\}/);

      if (jsonMatch) {
        return JSON.parse(jsonMatch[0]);
      } else {
        throw new Error('Failed to parse intent response');
      }

    } catch (error) {
      console.error('Intent analysis error:', error);
      // Возвращаем заглушку если AI не сработал
      return {
        intent: "other",
        dish: null,
        confidence: 0.1,
        response: "Какая-то дичь, повтори по-человечески!"
      };
    }
  }

  async analyzeDishType(dishName) {
    try {
      const prompt = `Проанализируй блюдо "${dishName}" и определи его тип. Ответь в формате JSON:

{
  "dishType": "одно из: meat, fish, soup, salad, pasta, dessert, other",
  "questions": ["список уточняющих вопросов для этого типа блюда"],
  "character": "краткая фраза-характеристика в стиле Гастро-ублюдка"
}

Правила:
- meat (мясо): спрашивай прожарку, способ приготовления, маринад
- fish (рыба): спрашивай термобработку, соус, способ готовки
- soup (суп): спрашивай консистенцию, заправку (сметана, зелень), хлеб
- salad (салат): спрашивай соус, основу, дополнительные ингредиенты
- pasta (паста): спрашивай соус, степень готовности, добавки
- dessert (десерт): спрашивай сладость, украшение, подачу

Пиши вопросы коротко и по делу. Добавь характер!`;

      const response = await axios.post(`${this.baseURL}/chat/completions`, {
        model: this.model,
        messages: [
          {
            role: 'system',
            content: 'Ты - эксперт-повар. Анализируй блюда и давай краткие рекомендации.'
          },
          {
            role: 'user',
            content: prompt
          }
        ],
        temperature: 0.5,
        max_tokens: 300
      }, {
        headers: {
          'Authorization': `Bearer ${this.apiKey}`,
          'Content-Type': 'application/json',
          'HTTP-Referer': 'https://t.me/gastro_ublyudok_bot',
          'X-Title': 'Gastro-Ublyudok'
        },
        timeout: 8000
      });

      const content = response.data.choices[0].message.content;
      const jsonMatch = content.match(/\{[\s\S]*\}/);

      if (jsonMatch) {
        return JSON.parse(jsonMatch[0]);
      } else {
        throw new Error('Failed to parse dish type response');
      }

    } catch (error) {
      console.error('Dish type analysis error:', error);
      // Fallback для разных типов блюд
      const dishLower = dishName.toLowerCase();

      if (dishLower.includes('стейк') || dishLower.includes('мясо') || dishLower.includes('котлета')) {
        return {
          dishType: 'meat',
          questions: ['Какую прожарку хочешь?'],
          character: 'Мясо! Отлично выбрал.'
        };
      } else if (dishLower.includes('суп') || dishLower.includes('борщ') || dishLower.includes('уха')) {
        return {
          dishType: 'soup',
          questions: ['Со сметаной будем или без?'],
          character: 'Суп - душа кухни!'
        };
      } else {
        return {
          dishType: 'other',
          questions: ['Какие детали уточнить?'],
          character: 'Интересный выбор...'
        };
      }
    }
  }

  async generateCreativeResponse(text, userContext = {}) {
    try {
      const prompt = `Отвечай на сообщение пользователя в стиле "Гастро-ублюдка". Ответь кратко, остроумно и грубовато, но по делу.

Сообщение: "${text}"
Уровень токсичности: ${userContext.insultMode || 'standard'}

Правила:
- Отвечай креативно, не шаблонно
- Используй кухонную метафору
- Будь остроумным, а не просто грубым
- Должен быть какой-то юмор
- Предложи вернуться к выбору блюд

Ответь просто текстом, без JSON.`;

      const response = await axios.post(`${this.baseURL}/chat/completions`, {
        model: this.model,
        messages: [
          {
            role: 'system',
            content: 'Ты - "Гастро-ублюдок", грубый но честный повар с отличным чувством юмора.'
          },
          {
            role: 'user',
            content: prompt
          }
        ],
        temperature: 0.8,
        max_tokens: 150
      }, {
        headers: {
          'Authorization': `Bearer ${this.apiKey}`,
          'Content-Type': 'application/json',
          'HTTP-Referer': 'https://t.me/gastro_ublyudok_bot',
          'X-Title': 'Gastro-Ublyudok'
        },
        timeout: 8000
      });

      return {
        response: response.data.choices[0].message.content
      };

    } catch (error) {
      console.error('Creative response error:', error);
      return {
        response: "Какая-то хуета. Давай по-нормальному: что жрать будем?"
      };
    }
  }
}

module.exports = OpenRouterService;