import { useState, useEffect, useRef, useCallback } from 'react';
import type { HighscoreEntry } from '../types';
import { submitHighscore, getHighscores } from '../api';

interface SnakeGameProps {
  userId: string;
  onClose: () => void;
}

type Direction = 'UP' | 'DOWN' | 'LEFT' | 'RIGHT';
type Position = { x: number; y: number };

const GRID_SIZE = 20;
const CELL_SIZE = 20; // px per cell
const CANVAS_SIZE = GRID_SIZE * CELL_SIZE; // 400px
const BASE_SPEED = 150; // ms per tick
const MIN_SPEED = 70;
const SPEED_DECREASE_PER_FOOD = 3;

const COURT_GREEN = '#2d5a27';
const COURT_LINE = 'rgba(255, 255, 255, 0.15)';
const TENNIS_BALL = '#ccff00';
const SNAKE_HEAD = '#4ade80';
const SNAKE_BODY = '#22c55e';

function randomFood(snake: Position[]): Position {
  let pos: Position;
  do {
    pos = {
      x: Math.floor(Math.random() * GRID_SIZE),
      y: Math.floor(Math.random() * GRID_SIZE),
    };
  } while (snake.some((s) => s.x === pos.x && s.y === pos.y));
  return pos;
}

export default function SnakeGame({ userId, onClose }: SnakeGameProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const gameLoopRef = useRef<number | null>(null);
  const directionRef = useRef<Direction>('RIGHT');
  const nextDirectionRef = useRef<Direction>('RIGHT');
  const snakeRef = useRef<Position[]>([
    { x: 5, y: 10 },
    { x: 4, y: 10 },
    { x: 3, y: 10 },
  ]);
  const foodRef = useRef<Position>(randomFood(snakeRef.current));
  const scoreRef = useRef(0);
  const touchStartRef = useRef<{ x: number; y: number } | null>(null);

  const [gameState, setGameState] = useState<'playing' | 'gameover'>('playing');
  const [score, setScore] = useState(0);
  const [highscores, setHighscores] = useState<HighscoreEntry[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [submitError, setSubmitError] = useState('');

  // Fetch highscores on mount
  useEffect(() => {
    getHighscores()
      .then((data) => setHighscores(data.slice(0, 10)))
      .catch(() => {});
  }, []);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Court background
    ctx.fillStyle = COURT_GREEN;
    ctx.fillRect(0, 0, CANVAS_SIZE, CANVAS_SIZE);

    // Court lines (subtle grid)
    ctx.strokeStyle = COURT_LINE;
    ctx.lineWidth = 0.5;
    for (let i = 0; i <= GRID_SIZE; i++) {
      ctx.beginPath();
      ctx.moveTo(i * CELL_SIZE, 0);
      ctx.lineTo(i * CELL_SIZE, CANVAS_SIZE);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(0, i * CELL_SIZE);
      ctx.lineTo(CANVAS_SIZE, i * CELL_SIZE);
      ctx.stroke();
    }

    // Center court line (tennis net)
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.4)';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(0, CANVAS_SIZE / 2);
    ctx.lineTo(CANVAS_SIZE, CANVAS_SIZE / 2);
    ctx.stroke();

    // Service boxes
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.2)';
    ctx.lineWidth = 1;
    ctx.strokeRect(
      CELL_SIZE * 3,
      CELL_SIZE * 3,
      CANVAS_SIZE - CELL_SIZE * 6,
      CANVAS_SIZE - CELL_SIZE * 6
    );

    // Food (tennis ball)
    const food = foodRef.current;
    ctx.fillStyle = TENNIS_BALL;
    ctx.beginPath();
    ctx.arc(
      food.x * CELL_SIZE + CELL_SIZE / 2,
      food.y * CELL_SIZE + CELL_SIZE / 2,
      CELL_SIZE / 2 - 2,
      0,
      Math.PI * 2
    );
    ctx.fill();

    // Tennis ball seam
    ctx.strokeStyle = '#a3cc00';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(
      food.x * CELL_SIZE + CELL_SIZE / 2,
      food.y * CELL_SIZE + CELL_SIZE / 2,
      CELL_SIZE / 2 - 4,
      -0.5,
      1.2
    );
    ctx.stroke();

    // Snake
    const snake = snakeRef.current;
    snake.forEach((seg, i) => {
      ctx.fillStyle = i === 0 ? SNAKE_HEAD : SNAKE_BODY;
      const padding = i === 0 ? 1 : 2;
      ctx.beginPath();
      ctx.roundRect(
        seg.x * CELL_SIZE + padding,
        seg.y * CELL_SIZE + padding,
        CELL_SIZE - padding * 2,
        CELL_SIZE - padding * 2,
        3
      );
      ctx.fill();
    });

    // Score overlay
    ctx.fillStyle = 'rgba(255, 255, 255, 0.9)';
    ctx.font = 'bold 14px system-ui, sans-serif';
    ctx.textAlign = 'left';
    ctx.fillText(`Score: ${scoreRef.current}`, 8, 18);
  }, []);

  const gameOver = useCallback(() => {
    if (gameLoopRef.current) {
      clearInterval(gameLoopRef.current);
      gameLoopRef.current = null;
    }
    setScore(scoreRef.current);
    setGameState('gameover');
    // Refresh highscores
    getHighscores()
      .then((data) => setHighscores(data.slice(0, 10)))
      .catch(() => {});
  }, []);

  const tick = useCallback(() => {
    const snake = [...snakeRef.current];
    const head = { ...snake[0] };

    directionRef.current = nextDirectionRef.current;

    switch (directionRef.current) {
      case 'UP':
        head.y -= 1;
        break;
      case 'DOWN':
        head.y += 1;
        break;
      case 'LEFT':
        head.x -= 1;
        break;
      case 'RIGHT':
        head.x += 1;
        break;
    }

    // Wall collision
    if (head.x < 0 || head.x >= GRID_SIZE || head.y < 0 || head.y >= GRID_SIZE) {
      gameOver();
      return;
    }

    // Self collision
    if (snake.some((s) => s.x === head.x && s.y === head.y)) {
      gameOver();
      return;
    }

    snake.unshift(head);

    // Food collision
    if (head.x === foodRef.current.x && head.y === foodRef.current.y) {
      scoreRef.current += 1;
      setScore(scoreRef.current);
      foodRef.current = randomFood(snake);

      // Speed up
      if (gameLoopRef.current) {
        clearInterval(gameLoopRef.current);
        const newSpeed = Math.max(MIN_SPEED, BASE_SPEED - scoreRef.current * SPEED_DECREASE_PER_FOOD);
        gameLoopRef.current = window.setInterval(() => {
          tick();
        }, newSpeed);
      }
    } else {
      snake.pop();
    }

    snakeRef.current = snake;
    draw();
  }, [draw, gameOver]);

  const startGame = useCallback(() => {
    snakeRef.current = [
      { x: 5, y: 10 },
      { x: 4, y: 10 },
      { x: 3, y: 10 },
    ];
    foodRef.current = randomFood(snakeRef.current);
    directionRef.current = 'RIGHT';
    nextDirectionRef.current = 'RIGHT';
    scoreRef.current = 0;
    setScore(0);
    setGameState('playing');
    setSubmitted(false);
    setSubmitError('');

    if (gameLoopRef.current) {
      clearInterval(gameLoopRef.current);
    }

    draw();

    gameLoopRef.current = window.setInterval(() => {
      tick();
    }, BASE_SPEED);
  }, [draw, tick]);

  // Start game on mount
  useEffect(() => {
    startGame();
    return () => {
      if (gameLoopRef.current) {
        clearInterval(gameLoopRef.current);
      }
    };
  }, [startGame]);

  // Keyboard controls
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const current = directionRef.current;
      switch (e.key) {
        case 'ArrowUp':
        case 'w':
        case 'W':
          if (current !== 'DOWN') nextDirectionRef.current = 'UP';
          e.preventDefault();
          break;
        case 'ArrowDown':
        case 's':
        case 'S':
          if (current !== 'UP') nextDirectionRef.current = 'DOWN';
          e.preventDefault();
          break;
        case 'ArrowLeft':
        case 'a':
        case 'A':
          if (current !== 'RIGHT') nextDirectionRef.current = 'LEFT';
          e.preventDefault();
          break;
        case 'ArrowRight':
        case 'd':
        case 'D':
          if (current !== 'LEFT') nextDirectionRef.current = 'RIGHT';
          e.preventDefault();
          break;
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Touch/swipe controls
  const handleTouchStart = (e: React.TouchEvent) => {
    const touch = e.touches[0];
    touchStartRef.current = { x: touch.clientX, y: touch.clientY };
  };

  const handleTouchEnd = (e: React.TouchEvent) => {
    if (!touchStartRef.current) return;
    const touch = e.changedTouches[0];
    const dx = touch.clientX - touchStartRef.current.x;
    const dy = touch.clientY - touchStartRef.current.y;
    touchStartRef.current = null;

    const minSwipe = 20;
    if (Math.abs(dx) < minSwipe && Math.abs(dy) < minSwipe) return;

    const current = directionRef.current;
    if (Math.abs(dx) > Math.abs(dy)) {
      if (dx > 0 && current !== 'LEFT') nextDirectionRef.current = 'RIGHT';
      else if (dx < 0 && current !== 'RIGHT') nextDirectionRef.current = 'LEFT';
    } else {
      if (dy > 0 && current !== 'UP') nextDirectionRef.current = 'DOWN';
      else if (dy < 0 && current !== 'DOWN') nextDirectionRef.current = 'UP';
    }
  };

  const handleSubmitScore = async () => {
    setSubmitting(true);
    setSubmitError('');
    try {
      await submitHighscore(userId, userId.split('@')[0], score);
      setSubmitted(true);
      // Refresh leaderboard
      const data = await getHighscores();
      setHighscores(data.slice(0, 10));
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosErr = err as { response?: { status?: number; data?: { error?: string } } };
        if (axiosErr.response?.status === 429) {
          setSubmitError('Please wait a few seconds before submitting again.');
        } else {
          setSubmitError(axiosErr.response?.data?.error || 'Failed to submit score.');
        }
      } else {
        setSubmitError('Failed to submit score.');
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />

      {/* Modal */}
      <div className="relative bg-white dark:bg-gray-800 rounded-xl shadow-xl border border-gray-200 dark:border-gray-700 w-full max-w-lg p-6 max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100 flex items-center gap-2">
            <span className="text-2xl">🐍</span> Snake Game
          </h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Game canvas */}
        <div className="flex justify-center mb-4">
          <canvas
            ref={canvasRef}
            width={CANVAS_SIZE}
            height={CANVAS_SIZE}
            className="rounded-lg border-2 border-green-700 dark:border-green-600"
            style={{ maxWidth: '100%', aspectRatio: '1', touchAction: 'none' }}
            onTouchStart={handleTouchStart}
            onTouchEnd={handleTouchEnd}
          />
        </div>

        {/* Controls hint */}
        {gameState === 'playing' && (
          <p className="text-xs text-gray-400 dark:text-gray-500 text-center mb-4">
            Arrow keys or WASD to move. Swipe on mobile.
          </p>
        )}

        {/* Game over panel */}
        {gameState === 'gameover' && (
          <div className="text-center mb-4">
            <p className="text-xl font-bold text-gray-900 dark:text-gray-100 mb-1">Game Over!</p>
            <p className="text-3xl font-bold text-green-600 dark:text-green-400 mb-4">
              Score: {score}
            </p>

            {submitError && (
              <div className="mb-3 bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-400 text-sm px-4 py-2 rounded-lg border border-red-200 dark:border-red-800">
                {submitError}
              </div>
            )}

            <div className="flex gap-3 justify-center">
              {!submitted ? (
                <button
                  onClick={handleSubmitScore}
                  disabled={submitting || score === 0}
                  className="bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white font-medium py-2 px-4 rounded-lg transition-colors flex items-center gap-2"
                >
                  {submitting && (
                    <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                  )}
                  Submit Score
                </button>
              ) : (
                <span className="text-green-600 dark:text-green-400 font-medium py-2 px-4">
                  Score submitted!
                </span>
              )}
              <button
                onClick={startGame}
                className="bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-300 font-medium py-2 px-4 rounded-lg transition-colors"
              >
                Play Again
              </button>
            </div>
          </div>
        )}

        {/* Leaderboard */}
        <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
          <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3 uppercase tracking-wide">
            Leaderboard
          </h3>
          {highscores.length === 0 ? (
            <p className="text-sm text-gray-400 dark:text-gray-500 text-center py-4">
              No scores yet. Be the first!
            </p>
          ) : (
            <div className="space-y-1.5">
              {highscores.map((entry, i) => (
                <div
                  key={entry.scoreId}
                  className={`flex items-center justify-between px-3 py-2 rounded-lg text-sm ${
                    i === 0
                      ? 'bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800'
                      : i < 3
                        ? 'bg-gray-50 dark:bg-gray-700/50'
                        : ''
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <span className={`w-6 text-center font-bold ${
                      i === 0 ? 'text-yellow-500' : i < 3 ? 'text-gray-500 dark:text-gray-400' : 'text-gray-400 dark:text-gray-500'
                    }`}>
                      {i === 0 ? '🥇' : i === 1 ? '🥈' : i === 2 ? '🥉' : `${i + 1}`}
                    </span>
                    <span className="text-gray-900 dark:text-gray-100 font-medium">
                      {entry.playerName}
                    </span>
                  </div>
                  <span className="font-bold text-green-600 dark:text-green-400">
                    {entry.score}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
