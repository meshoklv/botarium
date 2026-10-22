class InsultGenerator {
  static modes = {
    light: {
      greetings: [
        "Привет! Готов решать, что тебе пожрать сегодня.",
        "Так-так, кто тут проголодался?",
        "Ага, поймал тебя на мыслях о еде!"
      ],
      encouragements: [
        "Ну давай, справишься, я верю!",
        "Не переживай, всё получится!",
        "Ты молодец, решился готовить!"
      ],
      mistakes: [
        "Эй, внимательнее!",
        "Так, не торопись, всё по шагам.",
        "Упс, кажется что-то пошло не так."
      ],
      success: [
        "Отлично! Ты справился!",
        "Вот это я понимаю, результат!",
        "Готово! Можно приступать!"
      ]
    },
    standard: {
      greetings: [
        "Так, мясной мешок. Голодный? Определись, чего твоя душа просит, или я решу за тебя.",
        "Чего уставился как баран на новые ворота? Голоден, да?",
        "Ну что, желудок урчит? Пора решать, чем его заткнуть."
      ],
      encouragements: [
        "Давай, не тупи, делай как я говорю!",
        "Хватит сопли жевать, руки из жопы доставай!",
        "Неужели это так сложно? Движуйся!"
      ],
      mistakes: [
        "Какого хрена ты делаешь? Читать умеешь?",
        "Ты дурак? Я же сказал, как делать!",
        "Блин, да что тут сложного? Внимательнее смотри!"
      ],
      success: [
        "Ну наконец-то! А то я уже боялся, что ты посуду сожжешь.",
        "Нормально. Даже я удивлен, что у тебя получилось.",
        "Ладно, сойдет. Можно есть."
      ]
    },
    ramsey: {
      greetings: [
        "СУКА, ГДЕ ТЫ БЫЛ ВСЕ ЭТО ВРЕМЯ?! ТВОЙ ЖЕЛУДОК УЖЕ ПРАЗДНУЕТ, БЛЯТЬ!",
        "Хватит пялиться в потолок! Ты голоден, я голоден, давай решать, блять!",
        "Что за дегенерат не может решить, что поесть? Я сейчас тебе уши надеру!"
      ],
      encouragements: [
        "ДВИГАЙ СВОЮ ЖОПУ, БЛЯТЬ! ВРЕМЯ ИДЕТ!",
        "ТЫ ЧТО, СТАРЫЙ ДЕДУШКА? ДЕЛАЙ БЫСТРЕЕ!",
        "ХВАТИТ ЕБАНУТО СТОЯТЬ, РАБОТАЙ, УБЛЮДОК!"
      ],
      mistakes: [
        "ТЫ ОФИГЕЛ?! ЭТО ЖЕ ПРИМИТИВНО, СУКА!",
        "ДА ЧТО ТЫ НЕПОНЯТНЫЙ?! ЧИТАЙ БЛЯТЬ ВНИМАТЕЛЬНО!",
        "У МЕНЯ УЖЕ НЕРВЫ СКАЧУТ ОТ ТВОЕЙ ТУПОСТИ!"
      ],
      success: [
        "БЛЯТЬ, НАКОНЕЦ-ТО! МОЖЕТ, ТЫ НЕ ПОЛНЫЙ ИДИОТ?",
        "НУ СЛЫШЬ, А НЕПЛОХО! ДЛЯ ТЕБЯ ТО ЗАМЕЧАТЕЛЬНО!",
        "ГОТОВО, СУКА! ТЕПЕРЬ ЕШЬ И МОЛЧИ, ЧТОБ НЕ ОТРАВИТЬСЯ!"
      ]
    }
  };

  static getInsult(mode, type, context = {}) {
    const insults = this.modes[mode] || this.modes.standard;
    const category = insults[type] || insults.mistakes;

    // Выбираем случайное оскорбление из категории
    const insult = category[Math.floor(Math.random() * category.length)];

    // Добавляем контекст если нужно
    if (context.ingredient && type === 'mistakes') {
      return `${insult} Ты с ${context.ingredient} что, в детстве травился?`;
    }

    if (context.step && type === 'encouragements') {
      return `${insult} Это же всего лишь шаг ${context.step} из ${context.total}!`;
    }

    return insult;
  }

  static getCustomInsult(mode, template, replacements = {}) {
    let insult = template;

    Object.entries(replacements).forEach(([key, value]) => {
      insult = insult.replace(`{${key}}`, value);
    });

    return insult;
  }

  static getRandomInsult(mode) {
    const insults = this.modes[mode] || this.modes.standard;
    const allInsults = [
      ...insults.greetings,
      ...insults.encouragements,
      ...insults.mistakes,
      ...insults.success
    ];

    return allInsults[Math.floor(Math.random() * allInsults.length)];
  }
}

module.exports = InsultGenerator;