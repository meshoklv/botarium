const sqlite3 = require('sqlite3').verbose();
const config = require('../config');
const path = require('path');

class UserModel {
  constructor() {
    this.dbPath = path.resolve(config.database.path);
    this.init();
  }

  init() {
    this.db = new sqlite3.Database(this.dbPath);

    // Создаем таблицы
    this.db.serialize(() => {
      this.db.run(`
        CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY,
          telegram_id INTEGER UNIQUE,
          insult_mode TEXT DEFAULT 'standard',
          blacklist TEXT DEFAULT '[]',
          favorites TEXT DEFAULT '[]',
          dietary_preferences TEXT DEFAULT '{}',
          created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
          last_active DATETIME DEFAULT CURRENT_TIMESTAMP
        )
      `);

      this.db.run(`
        CREATE TABLE IF NOT EXISTS sessions (
          id INTEGER PRIMARY KEY,
          telegram_id INTEGER,
          state TEXT DEFAULT 'main',
          context TEXT DEFAULT '{}',
          created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY (telegram_id) REFERENCES users (telegram_id)
        )
      `);
    });
  }

  async getUser(telegramId) {
    return new Promise((resolve, reject) => {
      this.db.get(
        'SELECT * FROM users WHERE telegram_id = ?',
        [telegramId],
        (err, row) => {
          if (err) reject(err);
          else resolve(row);
        }
      );
    });
  }

  async createUser(telegramId) {
    return new Promise((resolve, reject) => {
      this.db.run(
        'INSERT INTO users (telegram_id) VALUES (?)',
        [telegramId],
        function(err) {
          if (err) reject(err);
          else resolve(this.lastID);
        }
      );
    });
  }

  async updateUser(telegramId, updates) {
    const setClause = Object.keys(updates).map(key => `${key} = ?`).join(', ');
    const values = Object.values(updates);

    return new Promise((resolve, reject) => {
      this.db.run(
        `UPDATE users SET ${setClause}, last_active = CURRENT_TIMESTAMP WHERE telegram_id = ?`,
        [...values, telegramId],
        function(err) {
          if (err) reject(err);
          else resolve(this.changes);
        }
      );
    });
  }

  async getOrCreateUser(telegramId) {
    let user = await this.getUser(telegramId);
    if (!user) {
      await this.createUser(telegramId);
      user = await this.getUser(telegramId);
    }
    return user;
  }

  async updateSession(telegramId, state, context = {}) {
    return new Promise((resolve, reject) => {
      this.db.run(
        `INSERT OR REPLACE INTO sessions (telegram_id, state, context, created_at)
         VALUES (?, ?, ?, CURRENT_TIMESTAMP)`,
        [telegramId, state, JSON.stringify(context)],
        function(err) {
          if (err) reject(err);
          else resolve(this.lastID);
        }
      );
    });
  }

  async getSession(telegramId) {
    return new Promise((resolve, reject) => {
      this.db.get(
        'SELECT * FROM sessions WHERE telegram_id = ?',
        [telegramId],
        (err, row) => {
          if (err) reject(err);
          else if (row) {
            resolve({
              ...row,
              context: JSON.parse(row.context)
            });
          } else {
            resolve(null);
          }
        }
      );
    });
  }

  async addToBlacklist(telegramId, item) {
    const user = await this.getOrCreateUser(telegramId);
    const blacklist = JSON.parse(user.blacklist || '[]');

    if (!blacklist.includes(item)) {
      blacklist.push(item);
      await this.updateUser(telegramId, { blacklist: JSON.stringify(blacklist) });
    }
  }

  async removeFromBlacklist(telegramId, item) {
    const user = await this.getUser(telegramId);
    if (user) {
      const blacklist = JSON.parse(user.blacklist || '[]');
      const filtered = blacklist.filter(i => i !== item);
      await this.updateUser(telegramId, { blacklist: JSON.stringify(filtered) });
    }
  }

  async addToFavorites(telegramId, recipe) {
    const user = await this.getOrCreateUser(telegramId);
    const favorites = JSON.parse(user.favorites || '[]');

    // Проверяем, нет ли уже такого рецепта
    if (!favorites.some(f => f.name === recipe.name)) {
      favorites.push({
        ...recipe,
        added_at: new Date().toISOString()
      });
      await this.updateUser(telegramId, { favorites: JSON.stringify(favorites) });
    }
  }

  async setInsultMode(telegramId, mode) {
    await this.updateUser(telegramId, { insult_mode: mode });
  }

  close() {
    this.db.close();
  }
}

module.exports = UserModel;