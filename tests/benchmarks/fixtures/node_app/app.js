#!/usr/bin/env node
/**
 * Express benchmark app with Sequelize, Joi validation, and auth libs.
 *
 * This app is used to benchmark snapshot restore times. It includes
 * real dependencies that exercise various Node.js ecosystems.
 *
 * Endpoints:
 * - GET /health - Simple health check
 * - GET /verify - Full verification (DB, validation, auth libs, lodash)
 * - POST /users - Create user (exercises full stack)
 */

const express = require('express');
const { Sequelize, DataTypes } = require('sequelize');
const Joi = require('joi');
const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');
const helmet = require('helmet');
const cors = require('cors');
const _ = require('lodash');
const moment = require('moment');
const { v4: uuidv4 } = require('uuid');

const app = express();
const SECRET_KEY = 'benchmark-secret-key-for-testing';
const STARTUP_TIME = Date.now();

// Middleware
app.use(express.json());
app.use(helmet());
app.use(cors());

// Database setup
const sequelize = new Sequelize({
  dialect: 'sqlite',
  storage: './benchmark.db',
  logging: false,
});

// User model
const User = sequelize.define('User', {
  id: {
    type: DataTypes.UUID,
    defaultValue: DataTypes.UUIDV4,
    primaryKey: true,
  },
  username: {
    type: DataTypes.STRING,
    unique: true,
    allowNull: false,
  },
  passwordHash: {
    type: DataTypes.STRING,
  },
});

// Validation schema
const userSchema = Joi.object({
  username: Joi.string().min(3).max(30).required(),
  password: Joi.string().min(6).required(),
});

// Routes
app.get('/health', (req, res) => {
  res.json({
    status: 'healthy',
    uptime_seconds: Math.round((Date.now() - STARTUP_TIME) / 1000 * 100) / 100,
  });
});

app.get('/verify', async (req, res) => {
  /**
   * Full verification endpoint - proves all dependencies work.
   *
   * This endpoint exercises:
   * - Sequelize: DB query
   * - Joi: Validation
   * - bcryptjs: Password hashing
   * - jsonwebtoken: JWT encoding
   * - lodash: Array operations
   * - moment: Date formatting
   * - uuid: ID generation
   */
  try {
    // Verify Sequelize DB connection
    const userCount = await User.count();

    // Verify Joi validation
    const { error } = userSchema.validate({ username: 'test', password: 'test123' });
    const joiOk = !error;

    // Verify bcryptjs
    const hash = await bcrypt.hash('test', 10);
    const bcryptOk = await bcrypt.compare('test', hash);

    // Verify jsonwebtoken
    const token = jwt.sign({ sub: 'test' }, SECRET_KEY);
    const decoded = jwt.verify(token, SECRET_KEY);
    const jwtOk = decoded.sub === 'test';

    // Verify lodash
    const arr = [1, 2, 3, 4, 5];
    const lodashOk = _.sum(arr) === 15;

    // Verify moment
    const momentOk = moment().isValid();

    // Verify uuid
    const testUuid = uuidv4();
    const uuidOk = testUuid.length === 36;

    res.json({
      status: 'verified',
      db_user_count: userCount,
      joi_ok: joiOk,
      bcrypt_ok: bcryptOk,
      jwt_ok: jwtOk,
      lodash_ok: lodashOk,
      moment_ok: momentOk,
      uuid_ok: uuidOk,
      all_ok: joiOk && bcryptOk && jwtOk && lodashOk && momentOk && uuidOk,
      timestamp: Date.now(),
    });
  } catch (e) {
    res.status(500).json({ status: 'error', error: e.message });
  }
});

app.post('/users', async (req, res) => {
  /**
   * Create a user - exercises full validation and DB stack.
   */
  try {
    const { error, value } = userSchema.validate(req.body);
    if (error) {
      return res.status(400).json({ error: error.details });
    }

    const passwordHash = await bcrypt.hash(value.password, 10);
    const user = await User.create({
      username: value.username,
      passwordHash,
    });

    res.status(201).json({ id: user.id, username: user.username });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// Initialize and start
(async () => {
  try {
    await sequelize.sync();
    console.log('Database synced');

    app.listen(5000, '0.0.0.0', () => {
      console.log('Express benchmark app listening on port 5000');
    });
  } catch (e) {
    console.error('Failed to start:', e);
    process.exit(1);
  }
})();
