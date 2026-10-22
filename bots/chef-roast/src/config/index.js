require('dotenv').config();

module.exports = {
  telegram: {
    token: process.env.TELEGRAM_BOT_TOKEN
  },
  openrouter: {
    apiKey: process.env.OPENROUTER_API_KEY,
    model: process.env.OPENROUTER_MODEL || 'deepseek/deepseek-chat-v3.1'
  },
  database: {
    path: process.env.DB_PATH || './data/database.db'
  },
  bot: {
    name: process.env.BOT_NAME || 'Гастро-ублюдок',
    defaultInsultMode: process.env.INSULT_MODE || 'standard'
  },
  safety: {
    // Список опасных ингредиентов которые не должен рекомендовать бот
    dangerousIngredients: [
      'сырые яйца', 'непрожаренное мясо', 'сырая рыба',
      'поганки', 'ядовитые грибы', 'бледная поганка',
      'мухомор', 'собачий гриб', 'ложные опята'
    ],
    // Запрещенные методы приготовления
    dangerousMethods: [
      'сыроедение', 'непрожарка', 'без термической обработки'
    ],
    // Обязательные предупреждения
    requiredWarnings: [
      'мясо птицы', 'свинина', 'рыба', 'морепродукты',
      'яйца', 'молочные продукты'
    ],
    // Минимальная температура приготовления для мяса
    safeCookingTemps: {
      chicken: 75,
      pork: 71,
      beef: 63,
      fish: 63
    }
  }
};