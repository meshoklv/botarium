const { Telegraf } = require('telegraf');
const config = require('./config');
const UserModel = require('./models/user');
const Keyboards = require('./keyboards/keyboards');
const InsultGenerator = require('./utils/insults');
const RecipeSafety = require('./utils/recipeSafety');
const OpenRouterService = require('./services/openrouter');

class GastroBot {
  constructor() {
    this.bot = new Telegraf(config.telegram.token);
    this.userModel = new UserModel();
    this.openRouter = new OpenRouterService();
    this.lastMessage = {}; // Храним последние сообщения для предотвращения повторов
    this.messageCount = {}; // Счетчик сообщений для антиспама
    this.setupHandlers();
  }

  setupHandlers() {
    // Команда /start
    this.bot.start(async (ctx) => {
      await this.handleStart(ctx);
    });

    // Команда /help
    this.bot.help(async (ctx) => {
      await this.handleHelp(ctx);
    });

    // Текстовые сообщения
    this.bot.on('text', async (ctx) => {
      await this.handleText(ctx);
    });

    // Callback кнопки
    this.bot.on('callback_query', async (ctx) => {
      await this.handleCallback(ctx);
    });
  }

  async handleStart(ctx) {
    const user = await this.userModel.getOrCreateUser(ctx.from.id);
    const insultMode = user.insult_mode || config.bot.defaultInsultMode;

    const greeting = InsultGenerator.getInsult(insultMode, 'greetings');

    await ctx.reply(`${greeting}`);

    await ctx.reply(`🍽️ *${config.bot.name}* здесь.`, {
      parse_mode: 'Markdown'
    });

    await ctx.reply('Хватит жрать хуйню. Я решу, чем тебе пожрать сегодня.', {
      reply_markup: Keyboards.main()
    });

    await this.userModel.updateSession(ctx.from.id, 'main', {});
  }

  async handleHelp(ctx) {
    const user = await this.userModel.getOrCreateUser(ctx.from.id);
    const insultMode = user.insult_mode || config.bot.defaultInsultMode;

    const insult = InsultGenerator.getInsult(insultMode, 'mistakes');

    await ctx.reply(`
${insult} Помощь нужна, да? Ладно, слушай:

🍽️ *Я знаю, чего хочу* - выбирай, что хошь жрать
🤷‍♂️ *Я тупая ленивая жопа* - я решу за тебя
⚙️ *Настройки* - уровень токсичности, черный список
📖 *Мои рецепты* - сохраненные хиты
🍷 *Алко-сомелье* - чем запивать твою жратву

Просто нажимай кнопки, не тупи!
    `, { parse_mode: 'Markdown' });
  }

  async handleText(ctx) {
    const userId = ctx.from.id;
    const text = ctx.message.text;

    // Проверка на спам и повторения
    if (this.isSpamOrDuplicate(userId, text)) {
      return; // Игнорируем спам и дубликаты
    }

    const session = await this.userModel.getSession(userId);
    const user = await this.userModel.getUser(userId);
    const insultMode = user.insult_mode || config.bot.defaultInsultMode;

    try {
      const currentState = session ? session.state : 'main';
      const context = session ? session.context || {} : {};

      // console.log(`Current state: ${currentState}, context:`, context); // Дебаг - отключено в проде

      switch (currentState) {
        case 'waiting_for_dish':
          // ПОЛЬЗОВАТЕЛЬ ВЫБРАЛ "Я ЗНАЮ, ЧЕГО ХОЧУ" - ждем название блюда
          await this.handleDishInput(ctx, text);
          break;

        case 'selecting_preparation':
          // Ждем уточнений по приготовлению (прожарка, соус и т.д.)
          await this.handlePreparationInput(ctx, text);
          break;

        case 'selecting_budget':
          // Ждем информацию о бюджете/ингредиентах
          await this.handleBudgetInput(ctx, text);
          break;

        case 'blacklist_add':
          await this.addToBlacklist(ctx, text);
          break;

        case 'waiting_for_drink_pairing':
          await this.processDrinkPairing(ctx, text);
          break;

        default:
          // ОСНОВНОЕ СОСТОЯНИЕ - анализируем намерение
          await this.handleMainInput(ctx, text);
      }

    } catch (error) {
      console.error('Text handler error:', error);
      const insult = InsultGenerator.getInsult(insultMode, 'mistakes');
      await ctx.reply(`${insult} Что-то сломалось, попробуй еще раз!`);
    }
  }

  // Метод для проверки спама и дубликатов
  isSpamOrDuplicate(userId, text) {
    const now = Date.now();

    // Инициализация счетчиков для нового пользователя
    if (!this.messageCount[userId]) {
      this.messageCount[userId] = { count: 0, lastTime: 0 };
    }

    if (!this.lastMessage[userId]) {
      this.lastMessage[userId] = { text: '', time: 0 };
    }

    // Проверка на дубликат (то же самое сообщение менее чем через 5 секунд)
    if (this.lastMessage[userId].text === text &&
        (now - this.lastMessage[userId].time) < 5000) {
      return true;
    }

    // Проверка на спам (более 5 сообщений за 10 секунд)
    if (this.messageCount[userId].count > 5 &&
        (now - this.messageCount[userId].lastTime) < 10000) {
      return true;
    }

    // Обновляем счетчики
    this.lastMessage[userId] = { text, time: now };
    this.messageCount[userId] = {
      count: this.messageCount[userId].count + 1,
      lastTime: now
    };

    // Сброс счетчика через минуту
    setTimeout(() => {
      if (this.messageCount[userId]) {
        this.messageCount[userId].count = Math.max(0, this.messageCount[userId].count - 1);
      }
    }, 60000);

    return false;
  }

  async handleMainInput(ctx, text) {
    const user = await this.userModel.getUser(ctx.from.id);
    const insultMode = user.insult_mode || config.bot.defaultInsultMode;

    try {
      // ПРЯМОЙ АНАЛИЗ БЕЗ ИИСКЛЮЧЕНИЙ
      const textLower = text.toLowerCase().trim();

      // Прямые команды
      if (textLower === '/start' || textLower === 'старт' || textLower === 'start') {
        await this.handleStart(ctx);
        return;
      }

      if (textLower === '/help' || textLower === 'помощь' || textLower === 'help') {
        await this.handleHelp(ctx);
        return;
      }

      if (textLower.includes('реши за меня') || textLower.includes('ленивый') || textLower.includes('подбери')) {
        await this.startLazyMode(ctx);
        return;
      }

      if (textLower.includes('случайный') || textLower.includes('рандом') || textLower.includes('сюрприз')) {
        await this.generateRandomRecipe(ctx);
        return;
      }

      if (textLower.includes('похудею') || textLower.includes('диета') || textLower.includes('калории')) {
        await this.generateDietRecipe(ctx);
        return;
      }

      if (textLower.includes('настройки') || textLower.includes('токсичность')) {
        await this.showSettings(ctx);
        return;
      }

      if (textLower.includes('рецепты') || textLower.includes('мои рецепты')) {
        await this.showMyRecipes(ctx);
        return;
      }

      if (textLower.includes('черный список') || textLower.includes('не хочу')) {
        await this.showBlacklist(ctx);
        return;
      }

      if (textLower.includes('алко') || textLower.includes('напитки') || textLower.includes('запивать')) {
        await this.alcoSommelier(ctx);
        return;
      }

      // Обработка прощаний
      if (textLower.includes('пока') || textLower.includes('до свидания') || textLower.includes('свидания')) {
        const insult = InsultGenerator.getInsult(insultMode, 'success');
        await ctx.reply(`${insult} Ушел так и не поев! Ну и иди нахуй тогда!`);
        return;
      }

      // Приветствия
      if (textLower.includes('привет') || textLower.includes('здравствуй') || textLower.includes('хай') || textLower.includes('ку')) {
        const insult = InsultGenerator.getInsult(insultMode, 'greetings');
        await ctx.reply(`${insult} Приветствую! Хватит жрать хуйню, давай решим, что приготовить.`, {
          reply_markup: Keyboards.main()
        });
        return;
      }

      // Проверка на вопросы о боте
      if (textLower.includes('бот') || textLower.includes('как дела') || textLower.includes('кто ты') || textLower.includes('понимаешь')) {
        const insult = InsultGenerator.getInsult(insultMode, 'mistakes');
        await ctx.reply(`${insult} Я твой личный повар, а не собеседник! Хочешь есть - давай, не хочешь - до свидания!`, {
          reply_markup: Keyboards.main()
        });
        return;
      }

      // Если написано название блюда или продукт - обрабатываем как запрос
      if (textLower.length > 2 &&
          !textLower.includes('бот') &&
          !textLower.includes('как дела') &&
          !textLower.includes('кто ты') &&
          !textLower.includes('почему') &&
          !textLower.includes('зачем') &&
          !textLower.includes('пока') &&
          !textLower.includes('свидания')) {
        await this.handleDishInput(ctx, text);
        return;
      }

      // Во всех остальных случаях - генерируем креативный ответ
      await this.handleUnknownInput(ctx, text);

    } catch (error) {
      console.error('Main input handler error:', error);
      const insult = InsultGenerator.getInsult(insultMode, 'mistakes');
      await ctx.reply(`${insult} Что-то сломалось, попробуй еще раз!`);
    }
  }

  
  async handleDonenessInput(ctx, text) {
    const session = await this.userModel.getSession(ctx.from.id);
    const { dishName, dishType } = session.context;
    const user = await this.userModel.getUser(ctx.from.id);
    const insultMode = user.insult_mode || config.bot.defaultInsultMode;

    // СОХРАНЯЕМ ВЫБОР ПОЛЬЗОВАТЕЛЯ
    await this.userModel.updateSession(ctx.from.id, 'selecting_budget', {
      dishName: dishName,
      dishType: dishType,
      preparation: text
    });

    const insult = InsultGenerator.getInsult(insultMode, 'encouragements');
    await ctx.reply(`${insult} Окей, ${text}.`);

    await ctx.reply('Теперь самое главное - какие ресурсы у тебя есть?', {
      reply_markup: Keyboards.budget()
    });
  }

  async handleBudgetInput(ctx, budget) {
    const session = await this.userModel.getSession(ctx.from.id);
    const { dishName, dishType, preparation } = session.context;
    const user = await this.userModel.getUser(ctx.from.id);
    const insultMode = user.insult_mode || config.bot.defaultInsultMode;

    // СОХРАНЯЕМ БЮДЖЕТ В КОНТЕКСТ
    session.context.budget = budget;
    await this.userModel.updateSession(ctx.from.id, 'generating_recipe', session.context);

    // ГЕНЕРИРУЕМ РЕЦЕПТ С РЕАЛЬНЫМИ ДАННЫМИ ИЗ СЕССИИ!
    await this.generateRecipeForDish(ctx, session.context);
  }

  async generateRecipeForDish(ctx, context) {
    // Проверяем наличие всех необходимых данных
    if (!context || !context.dishName) {
      const user = await this.userModel.getUser(ctx.from.id);
      const insultMode = user.insult_mode || config.bot.defaultInsultMode;
      const insult = InsultGenerator.getInsult(insultMode, 'mistakes');
      await ctx.reply(`${insult} Что-то пошло не так! Давай попробуем еще раз.`);
      await this.handleStart(ctx);
      return;
    }

    const { dishName, dishType = 'неизвестно', preparation = 'обычно', budget = 'стандартно' } = context;
    const user = await this.userModel.getUser(ctx.from.id);
    const insultMode = user.insult_mode || config.bot.defaultInsultMode;
    const blacklist = JSON.parse(user.blacklist || '[]');

    // console.log('Generating recipe with context:', context); // Дебаг - отключено в проде

    const insult = InsultGenerator.getInsult(insultMode, 'greetings');
    await ctx.reply(`${insult} Генерирую рецепт для "${dishName}"...`);

    try {
      // ИСПОЛЬЗУЕМ РЕАЛЬНЫЕ ДАННЫЕ ИЗ КОНТЕКСТА!
      const prompt = `Приготовь "${dishName}". Тип блюда: ${dishType}. Особенности приготовления: "${preparation}". Ингредиенты/бюджет: "${budget}". Сделай по-настоящему вкусно, а не как в столовке!`;

      const recipe = await this.openRouter.generateRecipe(prompt, {
        blacklist,
        insultMode,
        preferences: user.dietary_preferences || {}
      });

      const safetyCheck = RecipeSafety.validateRecipe(recipe);
      if (!safetyCheck.isSafe) {
        await ctx.reply('⚠️ Обнаружены проблемы с безопасностью. Генерирую новый рецепт...');
        return this.generateRecipeForDish(ctx, context);
      }

      const enhancedRecipe = safetyCheck.enhancedRecipe;

      await this.userModel.updateSession(ctx.from.id, 'recipe_generated', {
        recipe: enhancedRecipe,
        safetyWarnings: safetyCheck.warnings
      });

      await ctx.reply('✅ ГОТОВО!');

      const recipeName = enhancedRecipe.name || dishName || 'Неизвестное блюдо';
      await ctx.reply(`Сегодня твой удел — ${recipeName}.`);
      await ctx.reply('Дешево, сердито, охуенно. Готов записывать?', {
        reply_markup: Keyboards.confirmation()
      });

    } catch (error) {
      console.error('Recipe generation error:', error);
      const insult = InsultGenerator.getInsult(insultMode, 'mistakes');

      if (error.message.includes('попыток')) {
        await ctx.reply(`${insult} API сдох, блядь! Попробуй через пару минут.`);
      } else {
        await ctx.reply(`${insult} Что-то пошло не так, попробуй еще раз!`);
      }
    }
  }

  async handleUnknownInput(ctx, text) {
    const user = await this.userModel.getUser(ctx.from.id);
    const insultMode = user.insult_mode || config.bot.defaultInsultMode;
    const textLower = text.toLowerCase().trim();

    try {
      // Проверяем, не обработали ли мы уже этот текст
      if (textLower.includes('пидор') || textLower.includes('хуй') || textLower.includes('бля')) {
        const insult = InsultGenerator.getInsult(insultMode, 'mistakes');
        await ctx.reply(`${insult} Сам такой! Давай лучше поедим, а?`, {
          reply_markup: Keyboards.main()
        });
        return;
      }

      // Для непонятных сообщений - предлагаем варианты
      const insult = InsultGenerator.getInsult(insultMode, 'mistakes');
      await ctx.reply(`${text}? Интересно... Но я тут не для этого. Хочешь рецепт?`, {
        reply_markup: Keyboards.main()
      });

    } catch (error) {
      console.error('Unknown input handler error:', error);
      const insult = InsultGenerator.getInsult(insultMode, 'mistakes');
      await ctx.reply(`${insult} Что-то не понял. Давай так: выбери из меню!`, {
        reply_markup: Keyboards.main()
      });
    }
  }

  getPreparationText(prep) {
    const prepMap = {
      'sour_cream': 'Со сметаной',
      'herbs': 'С зеленью',
      'bread': 'С пампушками',
      'spicy': 'Посвежее',
      'mayonnaise': 'С майонезом',
      'olive_oil': 'С оливковым маслом',
      'bacon': 'С беконом',
      'cheese': 'С сыром',
      'rich': 'Пожирнее',
      'light': 'Полегче',
      'sweet': 'Послаще',
      'tomato_sauce': 'С томатным соусом',
      'meat_sauce': 'С мясным соусом',
      'cheese_sauce': 'С сырным соусом',
      'pesto': 'С песто'
    };
    return prepMap[prep] || prep;
  }

  getDonenessText(doneness) {
    const donenessMap = {
      'rare': 'Кровавый, как твоя бывшая',
      'medium': 'Нормально прожаренный',
      'well': 'Подошва, как ты любишь'
    };
    return donenessMap[doneness] || doneness;
  }

  // НОВЫЕ МЕТОДЫ ДЛЯ ПРАВИЛЬНОЙ РАБОТЫ

  async handleDishInput(ctx, dishName) {
    const user = await this.userModel.getUser(ctx.from.id);
    const insultMode = user.insult_mode || config.bot.defaultInsultMode;
    const dishNameLower = dishName.toLowerCase().trim();

    // Проверяем, не является ли это оскорблением
    if (dishNameLower.includes('пидор') || dishNameLower.includes('хуй') || dishNameLower.includes('бля')) {
      const insult = InsultGenerator.getInsult(insultMode, 'mistakes');
      await ctx.reply(`${insult} Сам такой! Может, поедим вместо этого?`, {
        reply_markup: Keyboards.main()
      });
      return;
    }

    // Специальная обработка для готовых продуктов
    if (dishNameLower.includes('мороженое') || dishNameLower.includes('пломбир') || dishNameLower.includes('эскимо')) {
      const insult = InsultGenerator.getInsult(insultMode, 'mistakes');
      await ctx.reply(`${insult} Мороженое? Это не готовка, это харчево! Открывай морозилку и ешь, блядь!`, {
        reply_markup: Keyboards.main()
      });
      return;
    }

    if (dishNameLower.includes('хлеб') || dishNameLower.includes('батон')) {
      const insult = InsultGenerator.getInsult(insultMode, 'mistakes');
      await ctx.reply(`${insult} Хлеб? Ты серьезно? Это не блюдо, это дополнение! Давай что-то поинтереснее.`, {
        reply_markup: Keyboards.main()
      });
      return;
    }

    if (dishNameLower.includes('колбаса') || dishNameLower.includes('сосиски') || dishNameLower.includes('сардельки')) {
      const insult = InsultGenerator.getInsult(insultMode, 'greetings');
      await ctx.reply(`${insult} Колбасные изделия? Можно и так! Жарить будем или как есть?`, {
        reply_markup: Keyboards.generalOptions()
      });
      return;
    }

    // СОХРАНЯЕМ БЛЮДО В СЕССИЮ ПЕРВЫМ ДЕЛОМ!
    await this.userModel.updateSession(ctx.from.id, 'selecting_preparation', {
      dishName: dishName,
      dishType: 'unknown',
      preparation: null,
      budget: null
    });

    // ОПРЕДЕЛЯЕМ ТИП БЛЮДА (без AI таймаутов!)
    const dishType = this.determineDishType(dishName);

    // ОБНОВЛЯЕМ ТИП БЛЮДА В СЕССИИ
    const session = await this.userModel.getSession(ctx.from.id);
    session.context.dishType = dishType;
    await this.userModel.updateSession(ctx.from.id, 'selecting_preparation', session.context);

    // ОДИН КОМПЛЕКТНЫЙ ОТВЕТ
    let response = '';
    let keyboard = null;

    switch (dishType) {
      case 'soup':
        response = `${dishName}? Отлично, не столовская хуйня. Со сметаной или без?`;
        keyboard = Keyboards.soupOptions();
        break;

      case 'meat':
        response = `${dishName}? Серьезный подход, одобряю. Какую прожарку?`;
        keyboard = Keyboards.meatDoneness();
        break;

      case 'pasta':
        response = `${dishName}? Не макароны по-флотски, надеюсь. Какой соус?`;
        keyboard = Keyboards.pastaOptions();
        break;

      case 'salad':
        response = `${dishName}? Полезно, блядь. С чем заправлять будем?`;
        keyboard = Keyboards.saladOptions();
        break;

      default:
        response = `${dishName}? Интересно... Давай уточним детали, чтобы не получилось как в столовке.`;
        keyboard = Keyboards.generalOptions();
    }

    await ctx.reply(response, {
      reply_markup: keyboard
    });
  }

  determineDishType(dishName) {
    const dishLower = dishName.toLowerCase();

    if (dishLower.includes('суп') || dishLower.includes('борщ') || dishLower.includes('уха') ||
        dishLower.includes('окрошка') || dishLower.includes('рассольник')) {
      return 'soup';
    }

    if (dishLower.includes('стейк') || dishLower.includes('мясо') || dishLower.includes('котлет') ||
        dishLower.includes('гуляш') || dishLower.includes('жаркое') || dishLower.includes('отбивная')) {
      return 'meat';
    }

    if (dishLower.includes('паста') || dishLower.includes('спагетти') || dishLower.includes('макароны')) {
      return 'pasta';
    }

    if (dishLower.includes('салат') || dishLower.includes('овощ')) {
      return 'salad';
    }

    return 'other';
  }

  async handlePreparationInput(ctx, text) {
    const session = await this.userModel.getSession(ctx.from.id);
    const { dishName, dishType } = session.context;
    const user = await this.userModel.getUser(ctx.from.id);
    const insultMode = user.insult_mode || config.bot.defaultInsultMode;

    // СОХРАНЯЕМ ВЫБОР ПОЛЬЗОВАТЕЛЯ
    session.context.preparation = text;
    await this.userModel.updateSession(ctx.from.id, 'selecting_budget', session.context);

    const insult = InsultGenerator.getInsult(insultMode, 'encouragements');

    // ОДИН ОТВЕТ НА ДЕЙСТВИЕ
    await ctx.reply(`${insult} Окей, ${text}. Что с ингредиентами?`, {
      reply_markup: Keyboards.budget()
    });
  }

  async handleCallback(ctx) {
    const action = ctx.callbackQuery.data;

    try {
      const user = await this.userModel.getOrCreateUser(ctx.from.id);
      const insultMode = user.insult_mode || config.bot.defaultInsultMode;

      await ctx.answerCbQuery();

    // Главное меню
    if (action === 'know_what_i_want') {
      const insult = InsultGenerator.getInsult(insultMode, 'encouragements');
      await ctx.reply(`${insult} Ну давай, удиви меня. Пиши или говори, что на уме. Только если это пельмени из пачки — иди нахуй отсюда.`);
      await this.userModel.updateSession(ctx.from.id, 'waiting_for_dish', {});
    } else if (action === 'lazy_mode') {
      await this.startLazyMode(ctx);
    } else if (action === 'settings') {
      await this.showSettings(ctx);
    } else if (action === 'my_recipes') {
      await this.showMyRecipes(ctx);
    } else if (action === 'alco_sommelier') {
      await this.alcoSommelier(ctx);
    }
    // Настройки
    else if (action.startsWith('insult_')) {
      const mode = action.replace('insult_', '');
      await this.userModel.setInsultMode(ctx.from.id, mode);
      const insult = InsultGenerator.getInsult(mode, 'success');
      await ctx.reply(`${insult} Уровень токсичности изменен!`);
      await this.showSettings(ctx);
    } else if (action === 'blacklist') {
      await this.showBlacklist(ctx);
    } else if (action === 'blacklist_add') {
      await ctx.reply('Что добавляем в черный список, блядь?');
      await this.userModel.updateSession(ctx.from.id, 'blacklist_add', {});
    }
    // Режим выбора блюда - прожарка мяса
    else if (action.startsWith('doneness_')) {
      const doneness = action.replace('doneness_', '');
      await this.handleDonenessInput(ctx, this.getDonenessText(doneness));
    } else if (action.startsWith('budget_')) {
      const budget = action.replace('budget_', '');
      await this.handleBudgetInput(ctx, budget);
    }
    // Ленивый режим
    else if (action.startsWith('time_')) {
      const time = action.replace('time_', '');
      await this.selectSkillLevel(ctx, time);
    } else if (action.startsWith('skill_')) {
      const skill = action.replace('skill_', '');
      await this.selectMood(ctx, skill);
    } else if (action.startsWith('mood_')) {
      const mood = action.replace('mood_', '');
      await this.generateRecipeForLazyMode(ctx, mood);
    }
    // Обработка новых кнопок приготовления
    else if (action.startsWith('prep_')) {
      const prep = action.replace('prep_', '');
      await this.handlePreparationInput(ctx, this.getPreparationText(prep));
    }
    // Навигация
    else if (action === 'back_to_main') {
      await this.handleStart(ctx);
    } else if (action === 'back_to_settings') {
      await this.showSettings(ctx);
    }
    // Рецепты
    else if (action === 'recipe_shopping') {
      await this.showShoppingList(ctx);
    } else if (action === 'recipe_steps') {
      await this.showRecipeSteps(ctx);
    } else if (action === 'recipe_drinks') {
      await this.showDrinkPairing(ctx);
    } else if (action === 'recipe_save') {
      await this.saveRecipe(ctx);
    } else if (action === 'confirm_recipe') {
      await this.confirmRecipe(ctx);
    } else if (action === 'reject_recipe') {
      const insult = InsultGenerator.getInsult(insultMode, 'mistakes');
      await ctx.reply(`${insult} Ну и иди нахуй тогда! Вернешься, когда решишь.`);
      await this.handleStart(ctx);
    }
    // Шаги рецепта
    else if (action.startsWith('step_')) {
      await this.navigateRecipeStep(ctx, action);
    }
    // Черный список - удаление элементов
    else if (action.startsWith('blacklist_remove_')) {
      const item = action.replace('blacklist_remove_', '');
      await this.removeFromBlacklist(ctx, item);
    }
    // Новые фичи
    else if (action === 'random_recipe') {
      await this.generateRandomRecipe(ctx);
    }
    else if (action === 'diet_mode') {
      await this.generateDietRecipe(ctx);
    }
        else if (action.startsWith('confirm_delete_')) {
      const item = action.replace('confirm_delete_', '');
      await this.confirmRemoveFromBlacklist(ctx, item);
    }
    else if (action === 'cancel_delete') {
      const insult = InsultGenerator.getInsult(insultMode, 'success');
      await ctx.reply(`${insult} Ну и правильно, передумал!`);
      await this.showBlacklist(ctx);
    }
    // Если action не распознан
    else {
      const insult = InsultGenerator.getInsult(insultMode, 'mistakes');
      await ctx.reply(`${insult} Что за хуйню ты нажал?`);
    }

    } catch (error) {
      console.error('Callback error:', error);
      const insult = InsultGenerator.getInsult('standard', 'mistakes');
      await ctx.reply(`${insult} Что-то сломалось, блядь! Попробуй еще раз.`);
    }
  }

  async startLazyMode(ctx) {
    const user = await this.userModel.getUser(ctx.from.id);
    const insultMode = user.insult_mode || config.bot.defaultInsultMode;

    const insult = InsultGenerator.getInsult(insultMode, 'greetings');

    await ctx.reply(`${insult} Классика. Мозг размером с грецкий орех.`);

    await ctx.reply('Ладно, твой поводырь здесь. Отвечай на три вопроса, и я сотворю кулинарное чудо.');

    await ctx.reply('⏰ *Вопрос 1: Время*', {
      parse_mode: 'Markdown'
    });

    await ctx.reply('Сколько времени у тебя есть на всё про всё? От похода в магаз до мытья посуды.', {
      reply_markup: Keyboards.cookingTime()
    });

    await this.userModel.updateSession(ctx.from.id, 'lazy_mode_time', {});
  }

  async selectSkillLevel(ctx, time) {
    const user = await this.userModel.getUser(ctx.from.id);
    const insultMode = user.insult_mode || config.bot.defaultInsultMode;

    const insult = InsultGenerator.getInsult(insultMode, 'encouragements');

    await ctx.reply(`⭐ *Вопрос 2: Скилл*`);

    await ctx.reply(`
${insult} Насколько у тебя руки из жопы растут по шкале от 1 до 5?

1 — могу сжечь воду
5 — сын Джейми Оливера
    `, {
      parse_mode: 'Markdown',
      reply_markup: Keyboards.skillLevel()
    });

    await this.userModel.updateSession(ctx.from.id, 'lazy_mode_skill', { time });
  }

  async selectMood(ctx, skill) {
    const session = await this.userModel.getSession(ctx.from.id);
    const user = await this.userModel.getUser(ctx.from.id);
    const insultMode = user.insult_mode || config.bot.defaultInsultMode;

    const insult = InsultGenerator.getInsult(insultMode, 'encouragements');

    await ctx.reply(`🎯 *Вопрос 3: Настроение*`);

    await ctx.reply(`${insult} Какое настроение у твоего желудка?`, {
      reply_markup: Keyboards.mood()
    });

    await this.userModel.updateSession(ctx.from.id, 'lazy_mode_mood', {
      time: session.context.time,
      skill
    });
  }

  async generateRecipeForLazyMode(ctx, mood) {
    const session = await this.userModel.getSession(ctx.from.id);
    const user = await this.userModel.getUser(ctx.from.id);
    const insultMode = user.insult_mode || config.bot.defaultInsultMode;

    // Проверяем наличие данных в сессии
    if (!session || !session.context || !session.context.time || !session.context.skill) {
      const insult = InsultGenerator.getInsult(insultMode, 'mistakes');
      await ctx.reply(`${insult} Что-то пошло не так! Начнем сначала.`);
      await this.startLazyMode(ctx);
      return;
    }

    const { time, skill } = session.context;
    const blacklist = JSON.parse(user.blacklist || '[]');

    const insult = InsultGenerator.getInsult(insultMode, 'greetings');

    await ctx.reply(`${insult} Думаю над твоим участьем...`);

    try {
      const prompt = this.buildLazyModePrompt(time, skill, mood, blacklist);
      const recipe = await this.openRouter.generateRecipe(prompt, {
        blacklist,
        insultMode,
        preferences: user.dietary_preferences || {}
      });

      // Проверка безопасности
      const safetyCheck = RecipeSafety.validateRecipe(recipe);
      if (!safetyCheck.isSafe) {
        await ctx.reply('⚠️ Обнаружены проблемы с рецептом. Генерирую новый...');
        return this.generateRecipeForLazyMode(ctx, mood);
      }

      const enhancedRecipe = safetyCheck.enhancedRecipe;

      // Сохраняем рецепт в сессии
      await this.userModel.updateSession(ctx.from.id, 'recipe_generated', {
        recipe: enhancedRecipe,
        safetyWarnings: safetyCheck.warnings
      });

      await ctx.reply('✅ РЕШЕНИЕ ПРИНЯТО!');

      // Проверяем наличие всех полей
      const recipeName = enhancedRecipe.name || 'Секретное блюдо';
      const recipeDescription = enhancedRecipe.description || 'Что-то вкусненькое';
      const recipePrepTime = enhancedRecipe.prepTime || '10 мин';
      const recipeCookTime = enhancedRecipe.cookTime || '20 мин';
      const recipeDifficulty = enhancedRecipe.difficulty || 3;
      const recipeServings = enhancedRecipe.servings || 1;

      await ctx.reply(`
*${recipeName}*

${recipeDescription}

⏰ ${recipePrepTime} + ${recipeCookTime}
🔥 Сложность: ${recipeDifficulty}/5
🍽️ Порций: ${recipeServings}
      `, {
        parse_mode: 'Markdown'
      });

      if (safetyCheck.warnings && safetyCheck.warnings.length > 0) {
        await ctx.reply(`\n🛡️ ${safetyCheck.warnings.join('\n')}`);
      }

      await ctx.reply('Возражения не принимаются.', {
        reply_markup: Keyboards.confirmation()
      });

    } catch (error) {
      console.error('Recipe generation error:', error);
      const insult = InsultGenerator.getInsult(insultMode, 'mistakes');

      if (error.message.includes('попыток')) {
        await ctx.reply(`${insult} API сдох! Попробуй через пару минут.`);
      } else if (error.message.includes('timeout')) {
        await ctx.reply(`${insult} Нейросеть тупит! Попробуй еще раз.`);
      } else {
        await ctx.reply(`${insult} Что-то пошло не так!`);
      }
    }
  }

  buildLazyModePrompt(time, skill, mood, blacklist) {
    const timeMap = {
      '15': 'максимум 15 минут',
      '40': 'около 40 минут',
      'evening': 'весь вечер'
    };

    const skillMap = {
      '1': 'полный новичок, могу сжечь воду',
      '3': 'средние навыки, что-то умею',
      '5': 'профи, сложные техники не проблема'
    };

    const moodMap = {
      'fatty': 'жирная, вредная, но охуенная еда',
      'light': 'что-то легкое, полезное, ЗОЖ-стиль',
      'asian': 'азиатская кухня, яркие вкусы',
      'grandma': 'домашняя еда, как у бабушки'
    };

    let prompt = `Придумай рецепт на ${timeMap[time]}. ` +
                 `Сложность: ${skillMap[skill]}. ` +
                 `Характер: ${moodMap[mood]}.`;

    if (blacklist.length > 0) {
      prompt += ` НИ В КОЕМ СЛУЧАЕ не используй: ${blacklist.join(', ')}.`;
    }

    return prompt;
  }

  async showSettings(ctx) {
    const user = await this.userModel.getUser(ctx.from.id);
    const insultMode = user.insult_mode || config.bot.defaultInsultMode;

    await ctx.reply('⚙️ НАСТРОЙКИ');

    const currentLevel = insultMode === 'light' ? '😊 Лайт' :
                       insultMode === 'standard' ? '😠 Стандарт' :
                       '🤬 Гордон Рамзи';

    await ctx.reply(`Текущий уровень токсичности: ${currentLevel}`);

    await ctx.reply('Выбери свой уровень:', {
      reply_markup: Keyboards.insultMode(insultMode)
    });
  }

  async showBlacklist(ctx) {
    const user = await this.userModel.getUser(ctx.from.id);
    const blacklist = JSON.parse(user.blacklist || '[]');

    if (blacklist.length === 0) {
      await ctx.reply('🚫 Черный список пуст. Добавь продукты, которые никогда не хочешь видеть!', {
        reply_markup: Keyboards.blacklist([])
      });
    } else {
      await ctx.reply(`🚫 Твой черный список:\n\n${blacklist.join('\n')}`, {
        reply_markup: Keyboards.blacklist(blacklist)
      });
    }
  }

  async addToBlacklist(ctx, item) {
    if (!item || item.trim().length === 0) {
      await ctx.reply('Ну и что ты добавляешь, блядь? Напиши нормально!');
      return;
    }

    try {
      await this.userModel.addToBlacklist(ctx.from.id, item.trim());
      const user = await this.userModel.getUser(ctx.from.id);
      const insultMode = user.insult_mode || config.bot.defaultInsultMode;

      const insult = InsultGenerator.getInsult(insultMode, 'success');
      await ctx.reply(`${insult} Добавил "${item}" в черный список. Больше увижу — убью.`);
      await this.showBlacklist(ctx);
    } catch (error) {
      console.error('Add to blacklist error:', error);
      await ctx.reply('Не смог добавить в черный список, попробуй еще раз!');
    }
  }

  async removeFromBlacklist(ctx, item) {
    try {
      await this.userModel.removeFromBlacklist(ctx.from.id, item);
      const user = await this.userModel.getUser(ctx.from.id);
      const insultMode = user.insult_mode || config.bot.defaultInsultMode;

      const insult = InsultGenerator.getInsult(insultMode, 'success');
      await ctx.reply(`${insult} Удалил "${item}" из черного списка. Теперь можешь жрать эту хуйню.`);
      await this.showBlacklist(ctx);
    } catch (error) {
      console.error('Remove from blacklist error:', error);
      await ctx.reply('Не смог удалить из черного списка, попробуй еще раз!');
    }
  }

  async confirmRecipe(ctx) {
    const session = await this.userModel.getSession(ctx.from.id);
    const user = await this.userModel.getUser(ctx.from.id);
    const insultMode = user.insult_mode || config.bot.defaultInsultMode;

    // Проверяем наличие сессии и рецепта
    if (!session || !session.context || !session.context.recipe) {
      const insult = InsultGenerator.getInsult(insultMode, 'mistakes');
      await ctx.reply(`${insult} Какой рецепт? Начни сначала!`);
      await this.handleStart(ctx);
      return;
    }

    const recipe = session.context.recipe;

    // Проверяем структуру рецепта
    if (!recipe.ingredients || !Array.isArray(recipe.ingredients)) {
      const insult = InsultGenerator.getInsult(insultMode, 'mistakes');
      await ctx.reply(`${insult} Рецепт кривой! Ингредиентов нету!`);
      return;
    }

    // Формируем список ингредиентов
    const ingredientsList = recipe.ingredients.map(ing => {
      if (!ing || typeof ing !== 'object') return '• ???';
      return `• ${ing.quantity || '???'} ${ing.unit || '???'} ${ing.name || '???'}`;
    }).join('\n');

    await ctx.reply('🛒 СПИСОК ПОКУПОК');

    await ctx.reply(ingredientsList);

    await ctx.reply('Сгоняй в магаз и не опозорься. Если спросишь, можно ли заменить гуанчиале на бекон — я тебя заблокирую.');

    await ctx.reply('Что дальше?', { reply_markup: Keyboards.recipeActions() });

    await this.userModel.updateSession(ctx.from.id, 'recipe_confirmed', { recipe });
  }

  async showMyRecipes(ctx) {
    const user = await this.userModel.getUser(ctx.from.id);
    const favorites = JSON.parse(user.favorites || '[]');
    const insultMode = user.insult_mode || config.bot.defaultInsultMode;

    if (favorites.length === 0) {
      const insult = InsultGenerator.getInsult(insultMode, 'mistakes');
      await ctx.reply(`${insult} У тебя нет сохраненных рецептов, ленивая жопа!`);
    } else {
      const recipesList = favorites.map((rec, index) =>
        `${index + 1}. ${rec.name} - ${rec.description}`
      ).join('\n\n');

      await ctx.reply(`❤️ ТВОИ РЕЦЕПТЫ:\n\n${recipesList}`);
    }

    await ctx.reply('', { reply_markup: Keyboards.management() });
  }

  async saveRecipe(ctx) {
    const session = await this.userModel.getSession(ctx.from.id);
    const user = await this.userModel.getUser(ctx.from.id);
    const insultMode = user.insult_mode || config.bot.defaultInsultMode;

    // Проверяем наличие сессии и рецепта
    if (!session || !session.context || !session.context.recipe) {
      const insult = InsultGenerator.getInsult(insultMode, 'mistakes');
      await ctx.reply(`${insult} Какой рецепт сохранить, блядь?`);
      return;
    }

    const recipe = session.context.recipe;

    // Проверяем структуру рецепта
    if (!recipe.name) {
      const insult = InsultGenerator.getInsult(insultMode, 'mistakes');
      await ctx.reply(`${insult} Рецепт без названия? В мусорку его!`);
      return;
    }

    try {
      await this.userModel.addToFavorites(ctx.from.id, recipe);
      const insult = InsultGenerator.getInsult(insultMode, 'success');
      await ctx.reply(`${insult} Рецепт "${recipe.name}" сохранен. Больше не будешь ебать мозг!`);
    } catch (error) {
      console.error('Save recipe error:', error);
      const insult = InsultGenerator.getInsult(insultMode, 'mistakes');
      await ctx.reply(`${insult} Не смог сохранить рецепт, блядь! Попробуй еще раз.`);
    }
  }

  
  async alcoSommelier(ctx) {
    const user = await this.userModel.getUser(ctx.from.id);
    const insultMode = user.insult_mode || config.bot.defaultInsultMode;
    const insult = InsultGenerator.getInsult(insultMode, 'greetings');

    await ctx.reply(`${insult} Чем запивать, спрашиваешь? Ну так скажи, какое блюдо у тебя!`, {
      reply_markup: Keyboards.main()
    });
    await this.userModel.updateSession(ctx.from.id, 'waiting_for_drink_pairing', {});
  }

  async processDrinkPairing(ctx, dishName) {
    const user = await this.userModel.getUser(ctx.from.id);
    const insultMode = user.insult_mode || config.bot.defaultInsultMode;

    try {
      await ctx.reply('🤔 Думаю, чем бы ты это запил...');

      const pairing = await this.openRouter.generateDrinkPairing(dishName, 'запрос пользователя');

      let response = `🍷 ЧЕМ ЗАПИВАТЬ *${dishName}*:\n\n`;
      pairing.pairings.forEach(pair => {
        response += `• *${pair.name}* (${pair.type})\n`;
        response += `  ${pair.reason}\n`;
        response += `  💰 ${pair.price}\n\n`;
      });

      await ctx.reply(response, {
        parse_mode: 'Markdown',
        reply_markup: Keyboards.main()
      });

    } catch (error) {
      console.error('Drink pairing error:', error);
      const insult = InsultGenerator.getInsult(insultMode, 'mistakes');
      await ctx.reply(`${insult} Ну если хочешь мой совет — пиво. Пиво ко всему подходит.`, {
        reply_markup: Keyboards.main()
      });
    }

    await this.userModel.updateSession(ctx.from.id, 'main', {});
  }

  async showDrinkPairing(ctx) {
    const session = await this.userModel.getSession(ctx.from.id);
    const recipe = session.context.recipe;

    if (!recipe) {
      await ctx.reply('Сначала выбери рецепт, алкаш!');
      return;
    }

    try {
      const pairing = await this.openRouter.generateDrinkPairing(recipe.name, recipe.description);

      let response = '🍷 ЧЕМ ЗАПИВАТЬ:\n\n';
      pairing.pairings.forEach(pair => {
        response += `• ${pair.name} (${pair.type})\n`;
        response += `  ${pair.reason}\n`;
        response += `  💰 ${pair.price}\n\n`;
      });

      await ctx.reply(response);

    } catch (error) {
      await ctx.reply('К этой пасте идеально зайдет легкое белое вино типа Пино Гриджио. Или пиво. Пиво ко всему подходит.');
    }
  }

  async showRecipeSteps(ctx) {
    const session = await this.userModel.getSession(ctx.from.id);
    const recipe = session.context.recipe;

    if (!recipe) {
      await ctx.reply('Какие шаги, блядь? Рецепта нет!');
      return;
    }

    await this.userModel.updateSession(ctx.from.id, 'recipe_steps', {
      recipe,
      currentStep: 1
    });

    await this.showStep(ctx, 1);
  }

  async showStep(ctx, stepNumber) {
    const session = await this.userModel.getSession(ctx.from.id);
    const user = await this.userModel.getUser(ctx.from.id);
    const insultMode = user.insult_mode || config.bot.defaultInsultMode;

    // Проверяем наличие сессии и рецепта
    if (!session || !session.context || !session.context.recipe) {
      const insult = InsultGenerator.getInsult(insultMode, 'mistakes');
      await ctx.reply(`${insult} Какой рецепт? Начни сначала!`, {
        reply_markup: Keyboards.main()
      });
      return;
    }

    const { recipe } = session.context;

    // Проверяем шаги
    if (!recipe.steps || stepNumber > recipe.steps.length || stepNumber < 1) {
      const insult = InsultGenerator.getInsult(insultMode, 'mistakes');
      await ctx.reply(`${insult} Некорректный шаг! Что-то сломалось.`, {
        reply_markup: Keyboards.main()
      });
      return;
    }

    const step = recipe.steps[stepNumber - 1];

    const encouragement = InsultGenerator.getInsult(insultMode, 'encouragements', {
      step: stepNumber,
      total: recipe.steps.length
    });

    // Определяем эмодзи для шага
    const stepEmoji = stepNumber === 1 ? '🚀' : stepNumber === recipe.steps.length ? '🏁' : '⚡';

    await ctx.reply(`
${stepEmoji} *ШАГ ${stepNumber}/${recipe.steps.length}*

${encouragement}

_${step}_

${stepNumber === recipe.steps.length ? '\n🎉 *ВСЕ ГОТОВО! Садись и ешь, пока не остыло!*' : ''}
    `, {
      parse_mode: 'Markdown',
      reply_markup: Keyboards.stepNavigation(stepNumber, recipe.steps.length)
    });

    await this.userModel.updateSession(ctx.from.id, 'recipe_steps', {
      recipe,
      currentStep: stepNumber
    });
  }

  async navigateRecipeStep(ctx, action) {
    if (action.includes('next')) {
      const stepNum = parseInt(action.split('_')[2]);
      await this.showStep(ctx, stepNum);
    } else if (action.includes('prev')) {
      const stepNum = parseInt(action.split('_')[2]);
      await this.showStep(ctx, stepNum);
    } else if (action === 'recipe_complete') {
      await ctx.reply('🏁 ГОТОВО! Садись и ешь, пока не остыло!', {
        reply_markup: Keyboards.main()
      });
    }
  }

  async showShoppingList(ctx) {
    const session = await this.userModel.getSession(ctx.from.id);
    const user = await this.userModel.getUser(ctx.from.id);
    const insultMode = user.insult_mode || config.bot.defaultInsultMode;

    if (!session || !session.context || !session.context.recipe) {
      const insult = InsultGenerator.getInsult(insultMode, 'mistakes');
      await ctx.reply(`${insult} Какой список, блядь? Рецепта нет!`, {
        reply_markup: Keyboards.main()
      });
      return;
    }

    const recipe = session.context.recipe;

    if (!recipe.ingredients || !Array.isArray(recipe.ingredients)) {
      const insult = InsultGenerator.getInsult(insultMode, 'mistakes');
      await ctx.reply(`${insult} В рецепте ингредиентов нету, кривой какой-то!`);
      return;
    }

    const ingredientsList = recipe.ingredients.map((ing, index) => {
      if (!ing || typeof ing !== 'object') return `${index + 1}. • ???`;
      return `${index + 1}. • *${ing.quantity || '???'}* ${ing.unit || '???'} *${ing.name || '???'}*`;
    }).join('\n');

    await ctx.reply(`
🛒 *СПИСОК ПОКУПОК*

_Сгоняй в магаз и не опозорься. Если спросишь, можно ли заменить гуанчиале на бекон — я тебя заблокирую._

${ingredientsList}

_✅ Список готов! Можно делать скриншот или просто отправлять себе в заметки._
    `, {
      parse_mode: 'Markdown',
      reply_markup: Keyboards.recipeActions()
    });
  }

  async generateRandomRecipe(ctx) {
    const user = await this.userModel.getUser(ctx.from.id);
    const insultMode = user.insult_mode || config.bot.defaultInsultMode;
    const insult = InsultGenerator.getInsult(insultMode, 'greetings');

    await ctx.reply(`${insult} Хочешь сюрприз, да? Ну получи случайный рецепт, может повезет...`);

    try {
      const blacklist = JSON.parse(user.blacklist || '[]');
      const prompt = 'Придумай ОЧЕНЬ необычный и интересный рецепт. Что-то, что человек точно никогда не пробовал.';

      const recipe = await this.openRouter.generateRecipe(prompt, {
        blacklist,
        insultMode,
        preferences: user.dietary_preferences || {}
      });

      const safetyCheck = RecipeSafety.validateRecipe(recipe);
      if (!safetyCheck.isSafe) {
        throw new Error('Небезопасный рецепт');
      }

      const enhancedRecipe = safetyCheck.enhancedRecipe;

      await this.userModel.updateSession(ctx.from.id, 'recipe_generated', {
        recipe: enhancedRecipe,
        safetyWarnings: safetyCheck.warnings
      });

      await ctx.reply(`
🎲 *СЛУЧАЙНЫЙ РЕЦЕПТ!*

*${enhancedRecipe.name}*

${enhancedRecipe.description}

⏰ Время: ${enhancedRecipe.prepTime} + ${enhancedRecipe.cookTime}
🔥 Сложность: ${enhancedRecipe.difficulty}/5

_Рискнуть и приготовить?_
      `, {
        parse_mode: 'Markdown',
        reply_markup: Keyboards.confirmation()
      });

    } catch (error) {
      console.error('Random recipe error:', error);
      const insult = InsultGenerator.getInsult(insultMode, 'mistakes');
      await ctx.reply(`${insult} Не смог придумать ничего интересного, попробуй еще раз!`);
    }
  }

  async generateDietRecipe(ctx) {
    const user = await this.userModel.getUser(ctx.from.id);
    const insultMode = user.insult_mode || config.bot.defaultInsultMode;
    const insult = InsultGenerator.getInsult(insultMode, 'greetings');

    await ctx.reply(`${insult} Так, решил похудеть, да? После Нового года, наверное...`);

    try {
      const blacklist = JSON.parse(user.blacklist || '[]');
      const prompt = 'Придумай низкокалорийный, но вкусный рецепт для похудения. Меньше 400 калорий на порцию.';

      const recipe = await this.openRouter.generateRecipe(prompt, {
        blacklist,
        insultMode,
        preferences: user.dietary_preferences || {}
      });

      const safetyCheck = RecipeSafety.validateRecipe(recipe);
      if (!safetyCheck.isSafe) {
        throw new Error('Небезопасный рецепт');
      }

      const enhancedRecipe = safetyCheck.enhancedRecipe;

      await this.userModel.updateSession(ctx.from.id, 'recipe_generated', {
        recipe: enhancedRecipe,
        safetyWarnings: safetyCheck.warnings
      });

      await ctx.reply(`
🥗 *ДИЕТ-РЕЦЕПТ*

*${enhancedRecipe.name}*

${enhancedRecipe.description}

⏰ Время: ${enhancedRecipe.prepTime} + ${enhancedRecipe.cookTime}
🔥 Сложность: ${enhancedRecipe.difficulty}/5
📊 Примерно: ~350 калорий

_Это точно вкуснее гречки на воде!_
      `, {
        parse_mode: 'Markdown',
        reply_markup: Keyboards.confirmation()
      });

    } catch (error) {
      console.error('Diet recipe error:', error);
      const insult = InsultGenerator.getInsult(insultMode, 'mistakes');
      await ctx.reply(`${insult} Даже не знаю, что посоветовать... Может, просто водой запьешь?`);
    }
  }

  
  async confirmRemoveFromBlacklist(ctx, item) {
    try {
      await this.userModel.removeFromBlacklist(ctx.from.id, item);
      const user = await this.userModel.getUser(ctx.from.id);
      const insultMode = user.insult_mode || config.bot.defaultInsultMode;

      const insult = InsultGenerator.getInsult(insultMode, 'success');
      await ctx.reply(`${insult} Удалил "${item}" из черного списка. Теперь можешь жрать эту хуйню.`);
      await this.showBlacklist(ctx);
    } catch (error) {
      console.error('Remove from blacklist error:', error);
      await ctx.reply('Не смог удалить из черного списка, попробуй еще раз!');
    }
  }

  async start() {
    console.log('🍽️ Гастро-ублюдок запускается...');

    this.bot.launch(() => {
      console.log('✅ Бот успешно запущен!');
    });

    // Graceful shutdown
    process.once('SIGINT', () => this.bot.stop('SIGINT'));
    process.once('SIGTERM', () => this.bot.stop('SIGTERM'));
  }
}

// Запуск бота
if (require.main === module) {
  const bot = new GastroBot();
  bot.start().catch(console.error);
}

module.exports = GastroBot;