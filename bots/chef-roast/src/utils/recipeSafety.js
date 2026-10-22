const config = require('../config');

class RecipeSafety {
  static validateRecipe(recipe) {
    const issues = [];
    const warnings = [];

    // Проверка на опасные ингредиенты
    recipe.ingredients.forEach(ingredient => {
      const dangerousFound = config.safety.dangerousIngredients.find(dangerous =>
        ingredient.name.toLowerCase().includes(dangerous.toLowerCase())
      );

      if (dangerousFound) {
        issues.push(`⚠️ ОПАСНО: Обнаружен опасный ингредиент - ${dangerousFound}. Рецепт не может быть использован!`);
      }
    });

    // Проверка на опасные методы приготовления
    recipe.steps.forEach(step => {
      const dangerousMethod = config.safety.dangerousMethods.find(method =>
        step.toLowerCase().includes(method.toLowerCase())
      );

      if (dangerousMethod) {
        issues.push(`⚠️ ОПАСНО: Обнаружен опасный метод приготовления - ${dangerousMethod}`);
      }
    });

    // Проверка на наличие предупреждений о продуктах
    config.safety.requiredWarnings.forEach(product => {
      if (recipe.ingredients.some(ing => ing.name.toLowerCase().includes(product.toLowerCase()))) {
        warnings.push(`🔥 ВНИМАНИЕ: Убедись, что ${product} тщательно прожарено/проварено!`);
      }
    });

    // Проверка температуры приготовления мяса
    if (recipe.meatType && config.safety.safeCookingTemps[recipe.meatType]) {
      const minTemp = config.safety.safeCookingTemps[recipe.meatType];
      if (!recipe.steps.some(step =>
        step.includes(`${minTemp}°C`) ||
        step.includes(`${minTemp} градусов`) ||
        step.includes('термометр') ||
        step.includes('проверь готовность')
      )) {
        warnings.push(`🌡️ ВАЖНО: ${recipe.meatType} нужно готовить до ${minTemp}°C внутри. Используй кухонный термометр!`);
      }
    }

    return {
      isSafe: issues.length === 0,
      issues,
      warnings,
      enhancedRecipe: this.enhanceRecipeWithSafety(recipe, warnings)
    };
  }

  static enhanceRecipeWithSafety(recipe, warnings) {
    const enhancedSteps = [...recipe.steps];

    // Добавляем проверки безопасности в начало рецепта
    if (warnings.length > 0) {
      enhancedSteps.unshift('🛡️ ПРОВЕРЬ БЕЗОПАСНОСТЬ: ' + warnings.join(' '));
    }

    // Добавляем общие правила безопасности
    enhancedSteps.push('🧼 ПОСЛЕ ПРИГОТОВЛЕНИЯ: Вымой руки, разделочную доску и инструменты горячей водой с мылом!');

    if (recipe.ingredients.some(ing => ing.name.toLowerCase().includes('мясо') ||
                                   ing.name.toLowerCase().includes('птица') ||
                                   ing.name.toLowerCase().includes('рыба'))) {
      enhancedSteps.push('🌡️ ЗАПОМНИ: Всегда проверяй готовность мяса термометром. Никаких "на глаз"!');
    }

    return {
      ...recipe,
      steps: enhancedSteps,
      safetyWarnings: warnings
    };
  }

  static sanitizeRecipePrompt(userPrompt) {
    // Убираем запросы на опасные вещи
    const dangerousKeywords = [
      'сыроедение', 'сырой', 'непрожаренный', 'кровавый',
      'ядовитый', 'собрать грибы', 'дикие грибы'
    ];

    let sanitized = userPrompt;
    dangerousKeywords.forEach(keyword => {
      if (sanitized.toLowerCase().includes(keyword)) {
        sanitized = sanitized.replace(new RegExp(keyword, 'gi'), 'безопасно приготовленный');
      }
    });

    return sanitized;
  }
}

module.exports = RecipeSafety;