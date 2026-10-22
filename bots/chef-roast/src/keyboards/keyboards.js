class Keyboards {
  // Главное меню - ReplyKeyboard (постоянные кнопки)
  static main() {
    return {
      keyboard: [
        [
          { text: '🍽️ Я знаю, чего хочу' },
          { text: '🤷‍♂️ Реши за меня' }
        ],
        [
          { text: '🎲 Случайный рецепт' },
          { text: '🔥 Похудею' }
        ],
        [
          { text: '⚙️ Настройки' },
          { text: '📖 Мои рецепты' }
        ],
        [
          { text: '🚫 Черный список' },
          { text: '🍷 Алко-сомелье' }
        ]
      ],
      resize_keyboard: true,
      one_time_keyboard: false
    };
  }

  // Главное меню - Inline (для одноразовых действий)
  static mainInline() {
    return {
      inline_keyboard: [
        [
          { text: '🍽️ Я знаю, чего хочу', callback_data: 'know_what_i_want' },
          { text: '🤷‍♂️ Реши за меня', callback_data: 'lazy_mode' }
        ],
        [
          { text: '🎲 Случайный рецепт', callback_data: 'random_recipe' },
          { text: '🔥 Похудею', callback_data: 'diet_mode' }
        ],
        [
          { text: '⚙️ Настройки', callback_data: 'settings' },
          { text: '📖 Мои рецепты', callback_data: 'my_recipes' }
        ],
        [
          { text: '🚫 Черный список', callback_data: 'blacklist' },
          { text: '🍷 Алко-сомелье', callback_data: 'alco_sommelier' }
        ]
      ]
    };
  }

  // Выбор уровня токсичности
  static insultMode(currentMode) {
    return {
      inline_keyboard: [
        [
          { text: currentMode === 'light' ? '✅ Лайт' : '😊 Лайт', callback_data: 'insult_light' }
        ],
        [
          { text: currentMode === 'standard' ? '✅ Стандарт' : '😠 Стандарт', callback_data: 'insult_standard' }
        ],
        [
          { text: currentMode === 'ramsey' ? '✅ Гордон Рамзи' : '🤬 Гордон Рамзи', callback_data: 'insult_ramsey' }
        ],
        [
          { text: '⬅️ Назад', callback_data: 'back_to_main' }
        ]
      ]
    };
  }

  // Выбор прожарки мяса
  static meatDoneness() {
    return {
      inline_keyboard: [
        [
          { text: '🔴 Кровавый, как твоя бывшая', callback_data: 'doneness_rare' },
          { text: '🟠 Нормально прожаренный', callback_data: 'doneness_medium' }
        ],
        [
          { text: '⚫️ Подошва, как ты любишь', callback_data: 'doneness_well' }
        ],
        [
          { text: '⬅️ Назад', callback_data: 'back_to_main' }
        ]
      ]
    };
  }

  // Выбор бюджета
  static budget() {
    return {
      inline_keyboard: [
        [
          { text: '💰 Деньги — не проблема', callback_data: 'budget_high' },
          { text: '💵 Бюджетненько, но со вкусом', callback_data: 'budget_medium' }
        ],
        [
          { text: '🏠 У меня есть кусок мяса', callback_data: 'budget_have_meat' }
        ],
        [
          { text: '⬅️ Назад', callback_data: 'back_to_main' }
        ]
      ]
    };
  }

  // Время приготовления
  static cookingTime() {
    return {
      inline_keyboard: [
        [{ text: '⚡ 15 мин', callback_data: 'time_15' },
         { text: '⏰ 40 мин', callback_data: 'time_40' },
         { text: '🌙 Весь вечер', callback_data: 'time_evening' }],
        [{ text: '⬅️ Назад', callback_data: 'back_to_main' }]
      ]
    };
  }

  // Уровень сложности
  static skillLevel() {
    return {
      inline_keyboard: [
        [{ text: '🥚 Безнадежен', callback_data: 'skill_1' },
         { text: '👨‍🍳 Нормально', callback_data: 'skill_3' },
         { text: '👑 Профи', callback_data: 'skill_5' }],
        [{ text: '⬅️ Назад', callback_data: 'back_to_main' }]
      ]
    };
  }

  // Настроение желудка
  static mood() {
    return {
      inline_keyboard: [
        [{ text: '🍔 Жирное', callback_data: 'mood_fatty' },
         { text: '🥗 Легкое', callback_data: 'mood_light' }],
        [{ text: '🥢 Азиатское', callback_data: 'mood_asian' },
         { text: '👵 Домашнее', callback_data: 'mood_grandma' }],
        [{ text: '⬅️ Назад', callback_data: 'back_to_main' }]
      ]
    };
  }

  // Действия с рецептом
  static recipeActions() {
    return {
      inline_keyboard: [
        [{ text: '🛒 Список покупок', callback_data: 'recipe_shopping' }],
        [{ text: '📝 Пошаговый план', callback_data: 'recipe_steps' }],
        [{ text: '🍷 Напитки', callback_data: 'recipe_drinks' }],
        [{ text: '❤️ Сохранить', callback_data: 'recipe_save' }],
        [{ text: '🏠 Меню', callback_data: 'back_to_main' }]
      ]
    };
  }

  // Подтверждение
  static confirmation() {
    return {
      inline_keyboard: [
        [{ text: '✅ Принято', callback_data: 'confirm_recipe' },
         { text: '❌ Другое', callback_data: 'reject_recipe' }]
      ]
    };
  }

  // Навигация по шагам
  static stepNavigation(currentStep, totalSteps) {
    const buttons = [];

    if (currentStep > 1) {
      buttons.push({ text: '⬅️ Предыдущий', callback_data: `step_prev_${currentStep - 1}` });
    }

    if (currentStep < totalSteps) {
      buttons.push({ text: 'Следующий ➡️', callback_data: `step_next_${currentStep + 1}` });
    }

    if (currentStep === totalSteps) {
      buttons.push({ text: '🏁 Готово!', callback_data: 'recipe_complete' });
    }

    buttons.push({ text: '🏠 Главное меню', callback_data: 'back_to_main' });

    return {
      inline_keyboard: [buttons]
    };
  }

  // Черный список
  static blacklist(items) {
    const buttons = items.map(item =>
      ({ text: `🗑️ ${item}`, callback_data: `blacklist_remove_${item}` })
    );

    // Добавляем по 2 кнопки в ряд
    const rows = [];
    for (let i = 0; i < buttons.length; i += 2) {
      rows.push(buttons.slice(i, i + 2));
    }

    rows.push([{ text: '➕ Добавить в черный список', callback_data: 'blacklist_add' }]);
    rows.push([{ text: '⬅️ Назад', callback_data: 'back_to_settings' }]);

    return {
      inline_keyboard: rows
    };
  }

  // Управление
  static management() {
    return {
      inline_keyboard: [
        [
          { text: '⚙️ Настройки', callback_data: 'settings' },
          { text: '📖 Мои рецепты', callback_data: 'my_recipes' }
        ],
        [
          { text: '🚫 Черный список', callback_data: 'blacklist' },
          { text: '🍷 Алко-сомелье', callback_data: 'alco_sommelier' }
        ],
        [
          { text: '🏠 Главное меню', callback_data: 'back_to_main' }
        ]
      ]
    };
  }

  // Опции для супов
  static soupOptions() {
    return {
      inline_keyboard: [
        [
          { text: '🥛 Со сметаной', callback_data: 'prep_sour_cream' },
          { text: '🌿 С зеленью', callback_data: 'prep_herbs' }
        ],
        [
          { text: '🥖 С пампушками', callback_data: 'prep_bread' },
          { text: '🌶️ Посвежее', callback_data: 'prep_spicy' }
        ],
        [
          { text: '⬅️ Назад', callback_data: 'back_to_main' }
        ]
      ]
    };
  }

  // Опции для салатов
  static saladOptions() {
    return {
      inline_keyboard: [
        [
          { text: '🥗 С майонезом', callback_data: 'prep_mayonnaise' },
          { text: '🫒 С оливковым', callback_data: 'prep_olive_oil' }
        ],
        [
          { text: '🥓 С беконом', callback_data: 'prep_bacon' },
          { text: '🧀 С сыром', callback_data: 'prep_cheese' }
        ],
        [
          { text: '⬅️ Назад', callback_data: 'back_to_main' }
        ]
      ]
    };
  }

  // Опции для пасты
  static pastaOptions() {
    return {
      inline_keyboard: [
        [
          { text: '🍝 С томатным соусом', callback_data: 'prep_tomato_sauce' },
          { text: '🥩 С мясным соусом', callback_data: 'prep_meat_sauce' }
        ],
        [
          { text: '🧀 С сырным соусом', callback_data: 'prep_cheese_sauce' },
          { text: '🌿 С песто', callback_data: 'prep_pesto' }
        ],
        [
          { text: '⬅️ Назад', callback_data: 'back_to_main' }
        ]
      ]
    };
  }

  // Общие опции
  static generalOptions() {
    return {
      inline_keyboard: [
        [
          { text: '🔥 Пожирнее', callback_data: 'prep_rich' },
          { text: '🥗 Полегче', callback_data: 'prep_light' }
        ],
        [
          { text: '🌶️ Поострее', callback_data: 'prep_spicy' },
          { text: '🍯 Послаще', callback_data: 'prep_sweet' }
        ],
        [
          { text: '⬅️ Назад', callback_data: 'back_to_main' }
        ]
      ]
    };
  }

  // Подтверждение удаления
  static confirmDelete(item) {
    return {
      inline_keyboard: [
        [
          { text: `✅ Да, удалить ${item}`, callback_data: `confirm_delete_${item}` },
          { text: '❌ Отмена', callback_data: 'cancel_delete' }
        ]
      ]
    };
  }
}

module.exports = Keyboards;